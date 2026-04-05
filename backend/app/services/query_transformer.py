"""Query transformation service for step-back prompting."""

import logging
import re
from typing import List, Optional

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

    async def transform(self, query: str) -> List[str]:
        """
        Transform a query into [original, step_back] or [original, step_back, hyde] versions.

        Exact, quoted, filename-specific, or very short queries skip transformation
        to avoid broadening into tangential results.

        Args:
            query: Original user query

        Returns:
            List containing original query, step-back variant, and optionally HyDE passage.
            On LLM error for step-back, returns [original] only.
            On HyDE failure alone, returns [original, step_back].
        """
        from app.config import settings

        # Skip transformation for exact/document-specific queries
        if _is_exact_or_document_query(query):
            logger.info(
                "Skipping query transformation for exact/document query: '%s'",
                query[:80],
            )
            return [query]

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
                messages=messages, max_tokens=100, temperature=0.3
            )

            if step_back and step_back.strip():
                logger.debug(
                    "Query transformation: original='%s', step_back='%s'",
                    query,
                    step_back,
                )
                variants = [query, step_back.strip()]
            else:
                logger.warning(
                    "Query transformation returned empty response, using original only"
                )
                return [query]

        except Exception as e:
            logger.warning(
                "Query transformation failed: %s, using original query only", e
            )
            return [query]

        # Optionally append HyDE passage as third query variant
        if settings.hyde_enabled:
            hyde_passage = await self.generate_hyde(query)
            if hyde_passage:
                variants.append(hyde_passage)

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
                messages, max_tokens=350, temperature=0.4
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
