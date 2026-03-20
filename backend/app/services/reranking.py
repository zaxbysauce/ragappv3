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
import threading
from typing import List, Dict, Any, Optional, Tuple

import httpx

from app.services.circuit_breaker import reranking_cb, CircuitBreakerError

logger = logging.getLogger(__name__)

_local_model = None  # lazy-loaded CrossEncoder instance
_model_lock = threading.Lock()  # lock for thread-safe lazy initialization


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

    async def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank chunks given a query. Returns top_n chunks sorted by score desc.

        Args:
            query: The user's query string.
            chunks: List of chunk dicts (must contain 'text' key).
            top_n: Override instance top_n for this call.

        Returns:
            Reranked and trimmed list of chunk dicts with '_rerank_score' added.
        """
        n = top_n or self.top_n
        if not chunks:
            return []
        if len(chunks) <= 1:
            return chunks

        texts = [c.get("text", "") for c in chunks]

        try:
            if self.reranker_url:
                scored = await self._rerank_via_endpoint(query, texts, n)
            else:
                scored = await self._rerank_local(query, texts, n)
        except Exception as e:
            logger.error(f"Reranking failed, returning original order: {e}")
            return chunks[:n]

        # Attach score and return top_n
        result = []
        for idx, score in scored:
            chunk = dict(chunks[idx])
            chunk["_rerank_score"] = score
            result.append(chunk)
        return result

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
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await reranking_cb(client.post)(url, json=payload)
                response.raise_for_status()
                data = response.json()
            except CircuitBreakerError:
                raise

        # data is list of {"index": int, "score": float}
        # Sort by score descending before slicing to ensure correct results
        sorted_data = sorted(data, key=lambda x: x.get("score", 0), reverse=True)
        return [(item["index"], item["score"]) for item in sorted_data[:top_n]]

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
            return indexed[:top_n]

        return await asyncio.to_thread(_score)
