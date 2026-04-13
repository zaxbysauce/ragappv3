"""Query transformation service for step-back prompting."""

import hashlib
import json
import logging
import re
from typing import List, Optional, Tuple

from app.config import settings
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _is_exact_or_document_query(query: str) -> bool:
    """Detect queries that should NOT be broadened by step-back/HyDE.

    Returns True for:
    - Quoted exact phrases ("some phrase")
    - Filename-specific queries (e.g., "in report.pdf", "from config.yaml")
    - Document-specific queries (e.g., "what does <filename> say about")
    - Very short exact lookups (3 words or fewer without question words)
    """
    # Quoted exact phrase
    if re.search(r'"[^"]{3,}"', query):
        return True
    # Filename reference (common extensions)
    if re.search(
        r'\b[\w\-]+\.(pdf|docx?|xlsx?|csv|txt|md|yaml|yml|json|html?|pptx?)\b',
        query,
        re.IGNORECASE,
    ):
        return True
    # Very short non-question lookups
    words = query.strip().split()
    question_words = {"what", "how", "why", "when", "where", "which", "who", "explain", "describe"}
    if len(words) <= 3 and not any(w.lower().rstrip("?") in question_words for w in words):
        return True
    return False


class QueryTransformer:
    """Transforms queries using step-back prompting for broader retrieval."""

    def __init__(self, llm_client: LLMClient):
        self._llm_client = llm_client
        self._redis_client = None
        if settings.redis_url:
            try:
                import redis
                self._redis_client = redis.from_url(settings.redis_url)
            except Exception as e:
                logger.warning("Redis connection failed, using LRU fallback: %s", e)
        # LRU cache for transform results (List[Tuple[str, str]])
        self._lru_cache: dict[str, List[Tuple[str, str]]] = {}
        self._lru_keys: list[str] = []  # For LRU ordering
        # Separate LRU cache for HyDE results (str)
        self._lru_hyde_cache: dict[str, str] = {}
        self._lru_hyde_keys: list[str] = []

    def _make_cache_key(self, chat_model: str, transform_type: str, query_text: str) -> str:
        """Generate cache key for query transformation result."""
        key_data = json.dumps({
            "model": chat_model,
            "type": transform_type,
            "query": query_text
        }, sort_keys=True)
        return f"query_transform:{hashlib.md5(key_data.encode()).hexdigest()}"

    def _lru_get(self, key: str) -> Optional[List[Tuple[str, str]]]:
        if key in self._lru_cache:
            # Move to end (most recently used)
            self._lru_keys.remove(key)
            self._lru_keys.append(key)
            return self._lru_cache[key]
        return None

    def _lru_set(self, key: str, value: List[Tuple[str, str]]):
        if key in self._lru_cache:
            self._lru_keys.remove(key)
        elif len(self._lru_cache) >= 1024:
            # Evict least recently used
            oldest = self._lru_keys.pop(0)
            del self._lru_cache[oldest]
        self._lru_cache[key] = value
        self._lru_keys.append(key)

    def _lru_get_hyde(self, key: str) -> Optional[str]:
        if key in self._lru_hyde_cache:
            # Move to end (most recently used)
            self._lru_hyde_keys.remove(key)
            self._lru_hyde_keys.append(key)
            return self._lru_hyde_cache[key]
        return None

    def _lru_set_hyde(self, key: str, value: str):
        if key in self._lru_hyde_cache:
            self._lru_hyde_keys.remove(key)
        elif len(self._lru_hyde_cache) >= 1024:
            # Evict least recently used
            oldest = self._lru_hyde_keys.pop(0)
            del self._lru_hyde_cache[oldest]
        self._lru_hyde_cache[key] = value
        self._lru_hyde_keys.append(key)

    async def transform(self, query: str) -> List[Tuple[str, str]]:
        """
        Transform a query into [original, step_back] or [original, step_back, hyde] versions.

        Exact, quoted, filename-specific, or very short queries skip transformation
        to avoid broadening into tangential results.

        Args:
            query: Original user query

        Returns:
            List of (variant_type, text) tuples containing original query, step-back variant,
            and optionally HyDE passage. variant_type values are 'original', 'step_back', 'hyde'.
            On LLM error for step-back, returns [('original', query)] only.
            On HyDE failure alone, returns [('original', query), ('step_back', step_back_text)].
        """
        # Skip transformation for exact/document-specific queries
        if _is_exact_or_document_query(query):
            logger.info(
                "Skipping query transformation for exact/document query: '%s'",
                query[:80],
            )
            return [('original', query)]

        # Check stepback_enabled gating
        if not settings.stepback_enabled:
            logger.debug("Step-back prompting disabled, returning original query only")
            return [('original', query)]

        # Generate cache key for step-back transformation
        cache_key = self._make_cache_key(settings.chat_model, "step_back", query)

        # Try Redis cache first
        if self._redis_client:
            try:
                cached = self._redis_client.get(cache_key)
                if cached:
                    logger.debug("Cache HIT (Redis) for query transformation")
                    return json.loads(cached)
            except Exception as e:
                logger.warning("Redis cache get failed: %s", e)

        # Try LRU cache
        lru_cached = self._lru_get(cache_key)
        if lru_cached:
            logger.debug("Cache HIT (LRU) for query transformation")
            return lru_cached

        # Cache miss - proceed with transformation
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a query transformation assistant. Your task is to generate "
                        "a broader, more general version of the user's question that captures "
                        "the high-level intent and underlying concepts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Generate a broader, more general version of this question that "
                        f"captures the underlying concept:\n"
                        f"Original: {query}\n"
                        f"Step-back:"
                    ),
                },
            ]

            step_back = await self._llm_client.chat_completion(
                messages=messages, max_tokens=100, temperature=settings.query_transform_temperature
            )

            if step_back and step_back.strip():
                logger.debug(
                    "Query transformation: original='%s', step_back='%s'",
                    query,
                    step_back,
                )
                variants: List[Tuple[str, str]] = [('original', query), ('step_back', step_back.strip())]
            else:
                logger.warning(
                    "Query transformation returned empty response, using original only"
                )
                variants: List[Tuple[str, str]] = [('original', query)]

        except Exception as e:
            logger.warning(
                "Query transformation failed: %s, using original query only", e
            )
            variants = [('original', query)]

        # Store in Redis if available
        if self._redis_client:
            try:
                self._redis_client.setex(
                    cache_key,
                    settings.query_transform_cache_ttl_sec,
                    json.dumps(variants)
                )
            except Exception as e:
                logger.warning("Redis cache set failed: %s", e)

        # Store in LRU cache
        self._lru_set(cache_key, variants)

        # Optionally append HyDE passage as third query variant
        if settings.hyde_enabled:
            # Check HyDE cache (both Redis and LRU)
            hyde_cache_key = self._make_cache_key(settings.chat_model, "hyde", query)
            hyde_passage = None
            
            # Try Redis first
            if self._redis_client:
                try:
                    cached_hyde = self._redis_client.get(hyde_cache_key)
                    if cached_hyde:
                        hyde_passage = json.loads(cached_hyde)
                except Exception as e:
                    logger.warning("Redis HyDE cache get failed: %s", e)
            
            # Try LRU fallback
            if not hyde_passage:
                hyde_passage = self._lru_get_hyde(hyde_cache_key)
            
            if hyde_passage is None:
                hyde_passage = await self.generate_hyde(query)
                if hyde_passage:
                    # Store in Redis if available
                    if self._redis_client:
                        try:
                            self._redis_client.setex(
                                hyde_cache_key,
                                settings.query_transform_cache_ttl_sec,
                                json.dumps(hyde_passage)
                            )
                        except Exception as e:
                            logger.warning("Redis HyDE cache set failed: %s", e)
                    # Store in LRU cache
                    self._lru_set_hyde(hyde_cache_key, hyde_passage)
            
            if hyde_passage:
                variants.append(('hyde', hyde_passage))

        return variants

    async def generate_hyde(self, query: str) -> Optional[str]:
        """
        Generate a hypothetical document passage that answers the query (HyDE).

        Args:
            query: The user question to generate a hypothetical answer for.

        Returns:
            A short factual passage (2-4 sentences) or None on failure/too-short response.
        """
        system_prompt = (
            "You are a knowledgeable assistant. Write a short, factual passage (2-4 sentences) "
            "that directly answers the following question. Write as if you are the document that "
            "contains the answer. Be specific and use domain-appropriate language. Do not hedge "
            "or say 'I think' — write as a confident factual passage."
        )
        user_prompt = f"Question: {query}\n\nPassage:"
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = await self._llm_client.chat_completion(
                messages, max_tokens=350, temperature=settings.hyde_temperature
            )
            response = response.strip()
            if len(response) < 20:
                logger.info(
                    "HyDE response too short (%d chars), discarding", len(response)
                )
                return None
            logger.info("HyDE passage generated for query '%s'", query[:60])
            return response
        except Exception as e:
            logger.warning("HyDE generation failed: %s", e)
            return None
