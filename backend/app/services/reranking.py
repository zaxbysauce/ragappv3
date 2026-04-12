"""
Cross-encoder reranking service for KnowledgeVault.

Supports two backends:
  1. TEI endpoint (if reranker_url is set): POST {url}/rerank
     Expected request:  {"query": str, "texts": [str], "top_n": int, "truncate": true}
     Expected response: [{"index": int, "score": float}, ...]
  2. Local sentence-transformers CrossEncoder (if reranker_url is empty).
     Model is loaded lazily on first use and cached.
"""

import logging
import math
import threading
from typing import List, Dict, Any, Optional, Tuple

import httpx

from app.services.circuit_breaker import reranking_cb, CircuitBreakerError

logger = logging.getLogger(__name__)

_local_model = None  # lazy-loaded CrossEncoder instance
_model_lock = threading.Lock()  # lock for thread-safe lazy initialization


def _safe_sigmoid(logit: float) -> float:
    """Unconditional sigmoid with overflow protection for BGE-M3 logits."""
    if logit > 709:
        return 1.0
    if logit < -709:
        return 0.0
    return 1.0 / (1.0 + math.exp(-logit))


def _get_local_model(model_id: str):
    """Lazy-load and cache a sentence-transformers CrossEncoder."""
    global _local_model
    if _local_model is None:
        with _model_lock:
            # Double-check after acquiring lock
            if _local_model is None:
                try:
                    from sentence_transformers import CrossEncoder
                    logger.info(f"Loading local CrossEncoder reranker: {model_id}")
                    _local_model = CrossEncoder(model_id)
                    logger.info("Local reranker loaded successfully")
                except ImportError:
                    raise RuntimeError(
                        "sentence-transformers is not installed. "
                        "Either set RERANKER_URL to a TEI endpoint, or add "
                        "'sentence-transformers>=2.7.0' to requirements.txt."
                    )
    return _local_model


class RerankingService:
    """
    Reranks a list of (chunk_dict) results given a query string.

    chunk_dict must have at minimum a 'text' key.
    Returns the top_n highest-scoring chunks, ordered by relevance descending.
    """

    def __init__(self, reranker_url: str, reranker_model: str, top_n: int = 5):
        self.reranker_url = reranker_url.rstrip("/") if reranker_url else ""
        self.reranker_model = reranker_model
        self.top_n = top_n
        self._http_client: Optional[httpx.AsyncClient] = None

    async def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Rerank chunks given a query. Returns top_n chunks sorted by score desc.

        Args:
            query: The user's query string.
            chunks: List of chunk dicts (must contain 'text' key).
            top_n: Override instance top_n for this call.

        Returns:
            Tuple of (reranked and trimmed list of chunk dicts with '_rerank_score', success).
        """
        n = top_n or self.top_n
        if not chunks:
            return ([], True)
        if len(chunks) <= 1:
            return (chunks, True)

        texts = [c.get("text", "") for c in chunks]

        try:
            if self.reranker_url:
                scored = await self._rerank_via_endpoint(query, texts, n)
            else:
                scored = await self._rerank_local(query, texts, n)
        except Exception as e:
            logger.error(f"Reranking failed, returning original order: {e}")
            return (chunks[:n], False)

        # Attach score and return top_n
        result = []
        for idx, score in scored:
            chunk = dict(chunks[idx])
            chunk["_rerank_score"] = score
            result.append(chunk)
        return (result, True)

    async def _rerank_via_endpoint(
        self, query: str, texts: List[str], top_n: int
    ) -> List[Tuple[int, float]]:
        """
        Call a TEI-compatible rerank endpoint.

        TEI format:
          POST /rerank
          Body: {"query": str, "texts": [str], "top_n": int, "truncate": true}
          Response: [{"index": int, "score": float}, ...]
        """
        url = f"{self.reranker_url}/rerank"
        payload = {
            "query": query,
            "texts": texts,
            "top_n": top_n,
            "truncate": True,
        }
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        try:
            response = await reranking_cb(self._http_client.post)(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except CircuitBreakerError:
            raise

        # data is list of {"index": int, "score": float}
        # Sort by score descending before slicing to ensure correct results
        sorted_data = sorted(data, key=lambda x: x.get("score", 0), reverse=True)
        raw_scores = [item["score"] for item in sorted_data[:top_n]]
        
        # Unconditional sigmoid with overflow protection for BGE-M3 logits
        normalized_scores = [_safe_sigmoid(score) for score in raw_scores]
        
        return [(item["index"], score) for item, score in zip(sorted_data[:top_n], normalized_scores)]

    async def close(self):
        """Close the persistent HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _rerank_local(
        self, query: str, texts: List[str], top_n: int
    ) -> List[Tuple[int, float]]:
        """
        Rerank using a locally loaded sentence-transformers CrossEncoder.
        Runs in a thread to avoid blocking the event loop.
        """
        import asyncio

        def _score():
            model = _get_local_model(self.reranker_model)
            pairs = [(query, text) for text in texts]
            scores = model.predict(pairs)
            indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            
            # Unconditional sigmoid with overflow protection for BGE-M3 logits
            raw_scores = [score for _, score in indexed[:top_n]]
            normalized_scores = [_safe_sigmoid(score) for score in raw_scores]
            
            return list(zip([idx for idx, _ in indexed[:top_n]], normalized_scores))

        return await asyncio.to_thread(_score)
