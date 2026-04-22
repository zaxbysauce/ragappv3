"""Context distillation: sentence-level deduplication and optional LLM synthesis."""

import logging
import math
import re
from typing import TYPE_CHECKING, List, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.embeddings import EmbeddingService
    from app.services.llm_client import LLMClient
    from app.services.rag_engine import RAGSource

_SYNTHESIS_PROMPT_SYSTEM = (
    "You are a precise document analyst. Given a user query and retrieved document "
    "passages, synthesize the most relevant information into a single coherent passage "
    "that directly addresses the query. Include only information present in the source "
    "passages — do not add outside knowledge."
)

_SYNTHESIS_PROMPT_USER = (
    "Query: {query}\n\n"
    "Source passages:\n{passages}\n\n"
    "Write a single synthesized passage (3-5 sentences maximum) that best answers the "
    "query using only the above sources. If the sources do not contain relevant "
    "information, respond with exactly: NO_RELEVANT_CONTENT"
)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences on sentence-ending punctuation followed by whitespace."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


class ContextDistiller:
    """
    Post-retrieval context distillation.

    1. Extractive deduplication: removes near-duplicate sentences across chunks.
    2. Optional LLM synthesis: synthesizes top-3 chunks when eval_result is
       NO_MATCH only (only when synthesis is enabled and llm_client provided).
    """

    def __init__(
        self,
        embedding_service: "EmbeddingService",
        llm_client: Optional["LLMClient"] = None,
    ) -> None:
        self._embedding_service = embedding_service
        self._llm_client = llm_client

    async def distill(
        self,
        query: str,
        sources: "List[RAGSource]",
        eval_result: str = "CONFIDENT",
    ) -> "List[RAGSource]":
        """
        Distill sources: deduplicate sentences, optionally synthesize for weak matches.

        Returns fewer or equal sources than input, never more.
        Fails open: embedding error returns sources unmodified.
        """
        from app.config import settings

        # Step 1: extractive deduplication
        try:
            sources = await self._deduplicate(
                sources, settings.context_distillation_dedup_threshold
            )
        except Exception as exc:
            logger.warning(
                "Context distillation dedup failed, returning unmodified: %s", exc
            )
            return sources

        # Step 2: optional LLM synthesis (only for weak matches)
        if (
            settings.context_distillation_synthesis_enabled
            and self._llm_client is not None
            and eval_result == "NO_MATCH"
            and sources
        ):
            sources = await self._synthesize(query, sources)

        return sources

    async def _deduplicate(
        self,
        sources: "List[RAGSource]",
        threshold: float,
    ) -> "List[RAGSource]":
        """Remove near-duplicate sentences from lower-ranked chunks."""
        # Collect all sentences with their source index
        all_sentences: List[str] = []
        sentence_map: List[tuple] = []  # (source_idx, sentence_pos)
        for src_idx, source in enumerate(sources):
            sentences = _split_sentences(source.text)
            for sent_pos, sent in enumerate(sentences):
                all_sentences.append(sent)
                sentence_map.append((src_idx, sent_pos))

        if not all_sentences:
            return sources

        # Embed all sentences in one batch call
        embeddings = await self._embedding_service.embed_batch(all_sentences)

        # Greedy dedup: keep sentence if not too similar to any previously kept sentence
        kept_embeddings: List[List[float]] = []
        is_dup: List[bool] = [False] * len(all_sentences)

        for i, emb in enumerate(embeddings):
            src_idx, _ = sentence_map[i]
            # First source's sentences are always kept (highest-ranked chunk wins)
            if src_idx == 0:
                kept_embeddings.append(emb)
                continue
            # Check similarity against all kept sentences
            dup = False
            for kept_emb in kept_embeddings:
                if _cosine_similarity(emb, kept_emb) > threshold:
                    dup = True
                    break
            if dup:
                is_dup[i] = True
            else:
                kept_embeddings.append(emb)

        # Reconstruct sources with duplicate sentences removed
        source_sentences: List[List[str]] = [[] for _ in sources]
        for i, (src_idx, _) in enumerate(sentence_map):
            if not is_dup[i]:
                source_sentences[src_idx].append(all_sentences[i])

        deduped: List = []
        for src_idx, source in enumerate(sources):
            new_text = " ".join(source_sentences[src_idx])
            if len(new_text) < 50:
                # Drop chunks reduced to near-nothing after dedup
                continue
            from app.services.rag_engine import RAGSource

            deduped.append(
                RAGSource(
                    text=new_text,
                    file_id=source.file_id,
                    score=source.score,
                    metadata=source.metadata,
                )
            )

        return deduped

    async def _synthesize(
        self,
        query: str,
        sources: "List[RAGSource]",
    ) -> "List[RAGSource]":
        """Synthesize top-3 chunks into a single coherent passage via LLM."""
        top3 = sources[:3]
        rest = sources[3:]

        passages = "\n---\n".join(src.text for src in top3)
        user_msg = _SYNTHESIS_PROMPT_USER.format(query=query, passages=passages)

        try:
            messages = [
                {"role": "system", "content": _SYNTHESIS_PROMPT_SYSTEM},
                {"role": "user", "content": user_msg},
            ]
            result = await self._llm_client.chat_completion(
                messages, max_tokens=300, temperature=0.1
            )
            result = result.strip()
        except Exception as exc:
            logger.warning("Context distillation synthesis LLM call failed: %s", exc)
            return sources  # fail-open: return deduplicated sources

        if not result or result == "NO_RELEVANT_CONTENT":
            # Synthesis found nothing useful — pass through deduplicated chunks
            return sources

        from app.services.rag_engine import RAGSource

        synthetic = RAGSource(
            text=result,
            file_id=top3[0].file_id if top3 else "",
            score=top3[0].score if top3 else 0.0,
            metadata={"synthesized": True},
        )
        return [synthetic] + rest
