"""Retrieval-augmented generation engine orchestration."""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

from app.config import settings
from app.services.citation_validator import (
    parse_citations,
    repair_against_sources_and_memories,
)
from app.services.context_distiller import ContextDistiller
from app.services.document_retrieval import DocumentRetrievalService, RAGSource
from app.services.embeddings import EmbeddingError, EmbeddingService
from app.services.llm_client import LLMClient, LLMError
from app.services.memory_store import MemoryStore
from app.services.prompt_builder import PromptBuilderService, calculate_primary_count
from app.services.query_transformer import QueryTransformer
from app.services.rag_trace import RAGTrace
from app.services.retrieval_evaluator import RetrievalEvaluator
from app.services.vector_store import VectorStore
from app.utils.fusion import rrf_fuse


def _get_pool():
    """Deferred import to avoid circular dependency."""
    from app.models.database import get_pool

    return get_pool(str(settings.sqlite_path))


logger = logging.getLogger(__name__)


class RAGEngineError(Exception):
    """Raised when the RAG engine cannot complete a query."""


class RAGEngine:
    """Coordinates embeddings, vector search, memory search, and LLM responses."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        vector_store: Optional[Any] = None,
        memory_store: Optional[MemoryStore] = None,
        llm_client: Optional[LLMClient] = None,
        reranking_service: Optional[Any] = None,
        document_retrieval_service: Optional[DocumentRetrievalService] = None,
        prompt_builder_service: Optional[PromptBuilderService] = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or None
        self.memory_store = memory_store or MemoryStore()
        self.llm_client = llm_client or LLMClient()
        self.reranking_service = reranking_service

        # Log warnings for missing dependencies (indicates non-DI usage)
        if embedding_service is None:
            logger.warning(
                "RAGEngine created without injected embedding_service - using default instance"
            )
        if vector_store is None:
            logger.warning(
                "RAGEngine created without injected vector_store - using default instance"
            )
        if memory_store is None:
            logger.warning(
                "RAGEngine created without injected memory_store - using default instance"
            )
        if llm_client is None:
            logger.warning(
                "RAGEngine created without injected llm_client - using default instance"
            )

        # Initialize vector store if not provided
        if self.vector_store is None:
            self.vector_store = VectorStore()

        # Use new character-based fields, with fallback to legacy fields for backward compatibility
        self.chunk_size_chars = settings.chunk_size_chars
        self.chunk_overlap_chars = settings.chunk_overlap_chars
        self.retrieval_top_k = settings.retrieval_top_k
        self.vector_metric = settings.vector_metric
        self.max_distance_threshold = settings.max_distance_threshold
        self.embedding_doc_prefix = settings.embedding_doc_prefix
        self.embedding_query_prefix = settings.embedding_query_prefix
        self.retrieval_window = settings.retrieval_window

        # Reranking config
        self.reranking_enabled = settings.reranking_enabled
        self.reranker_top_n = settings.reranker_top_n
        self.initial_retrieval_top_k = settings.initial_retrieval_top_k

        # Hybrid search config
        self.hybrid_search_enabled = settings.hybrid_search_enabled
        self.hybrid_alpha = settings.hybrid_alpha

        # Legacy field support (deprecated) - warn if different from canonical fields
        self.relevance_threshold = settings.rag_relevance_threshold
        self.top_k = settings.vector_top_k
        if self.top_k is not None and self.top_k != self.retrieval_top_k:
            logger.warning(
                "vector_top_k (%s) is deprecated and differs from retrieval_top_k (%s). "
                "Using retrieval_top_k. Please update your settings.",
                self.top_k,
                self.retrieval_top_k,
            )
        self.maintenance_mode = settings.maintenance_mode

        # Initialize extracted services (lazy initialization if not provided)
        if document_retrieval_service:
            self.document_retrieval = document_retrieval_service
        else:
            self.document_retrieval = DocumentRetrievalService(
                vector_store=self.vector_store,
                max_distance_threshold=self.max_distance_threshold,
                retrieval_top_k=self.retrieval_top_k,
                retrieval_window=self.retrieval_window,
            )

        if prompt_builder_service:
            self.prompt_builder = prompt_builder_service
        else:
            self.prompt_builder = PromptBuilderService()

        # Query transformer instance (lazy-loaded)
        self._query_transformer: Optional[QueryTransformer] = None

        # Retrieval evaluator instance (lazy-loaded)
        self._retrieval_evaluator: Optional[RetrievalEvaluator] = None

    async def query(
        self,
        user_input: str,
        chat_history: List[Dict[str, Any]],
        stream: bool = False,
        vault_id: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute a RAG query: embed, search, build prompt, call LLM."""
        logger.info(
            "[query] START: user_input_len=%d, vault_id=%s, stream=%s",
            len(user_input),
            vault_id,
            stream,
        )
        # Per-query observability accumulator. Always built; emitted into
        # the done message only when ``rag_trace_in_response`` is on.
        trace = RAGTrace(original_query=user_input)
        trace.distance_threshold = self.max_distance_threshold
        # Memory intent detection
        try:
            memory_content = self.memory_store.detect_memory_intent(user_input)
            if memory_content:
                memory = await asyncio.to_thread(
                    self.memory_store.add_memory, memory_content, source="chat", vault_id=vault_id
                )
                yield {
                    "type": "content",
                    "content": f"Memory stored: {memory.content}",
                }
                yield {"type": "done"}
                return
        except Exception as exc:
            logger.error("Memory intent detection/add failed (%s): %s", type(exc).__name__, exc)

        # Query transformation for broader retrieval (if enabled)
        transformed_queries: List[Tuple[str, str]] = [('original', user_input)]
        if settings.query_transformation_enabled and self.llm_client is not None:
            try:
                if self._query_transformer is None:
                    self._query_transformer = QueryTransformer(self.llm_client)
                transformed_queries = await self._query_transformer.transform(
                    user_input
                )
                # transformed_queries is now List[Tuple[str, str]] like [('original', '...'), ('step_back', '...'), ('hyde', '...')]
                if len(transformed_queries) > 1:
                    logger.info(
                        "Query transformation: original='%s', step_back='%s'",
                        transformed_queries[0][1],
                        transformed_queries[1][1],
                    )
                trace.transformed_queries = [t[1] for t in transformed_queries]
            except Exception as e:
                logger.warning(
                    "Query transformation failed (%s): %s, using original query only", type(e).__name__, e
                )
                transformed_queries = [('original', user_input)]

        logger.debug("[query] transformed_queries=%s", transformed_queries)

        # Embed all transformed queries concurrently
        # query_embeddings will be List[Tuple[str, List[float]]] where tuple is (variant_type, embedding)
        query_embeddings: List[Tuple[str, List[float]]] = []
        variants_dropped: List[str] = []

        async def _embed_one(vtype: str, text: str) -> List[float]:
            if vtype == 'hyde':
                return await self.embedding_service.embed_passage(text)
            return await self.embedding_service.embed_single(text)

        embed_tasks = [_embed_one(vt, t) for vt, t in transformed_queries]
        raw_embeddings = await asyncio.gather(*embed_tasks, return_exceptions=True)

        for (variant_type, _), result in zip(transformed_queries, raw_embeddings):
            if isinstance(result, EmbeddingError):
                if variant_type == 'original':
                    logger.error(
                        "Query embedding failure for original query: %s", result
                    )
                    raise RAGEngineError(f"Original query embedding failed: {result}")
                logger.warning(
                    "Query embedding failure for variant '%s': %s", variant_type, result
                )
                variants_dropped.append(variant_type)
            elif isinstance(result, BaseException):
                if variant_type == 'original':
                    logger.error("Query embedding failure for original query: %s", result)
                    raise RAGEngineError(f"Original query embedding failed: {result}")
                variants_dropped.append(variant_type)
            else:
                query_embeddings.append((variant_type, result))

        if not query_embeddings:
            error_msg = "Unable to encode any query variants"
            logger.error(
                "[query] No query embeddings produced — all embedding attempts failed"
            )
            if stream:
                yield {"type": "error", "message": error_msg, "code": "EMBEDDING_ERROR"}
                return
            raise RAGEngineError(error_msg)

        logger.info(
            "[query] query_embeddings: count=%d, dim=%s",
            len(query_embeddings),
            len(query_embeddings[0][1]) if query_embeddings else "N/A",
        )

        effective_alpha = self.hybrid_alpha

        # Execute retrieval and evaluation
        fallback_reason: Optional[str] = None
        vector_results: List[Dict[str, Any]] = []
        relevance_hint: Optional[str] = None

        logger.debug(
            "RAG query: retrieval_top_k=%d, vault_id=%s, vector_store_connected=%s",
            self.retrieval_top_k,
            vault_id,
            getattr(self.vector_store, "is_connected", lambda: "unknown")(),
        )

        eval_result = "CONFIDENT"
        rerank_success: Optional[bool] = None
        # Initialize variables that will be set by _execute_retrieval (or fallback values)
        score_type = "distance"
        hybrid_status = "disabled"
        fts_exceptions = 0
        rerank_status = "disabled"
        exact_match_promoted = False
        token_pack_stats: Dict[str, int] = {
            "token_pack_included": 0,
            "token_pack_skipped": 0,
            "token_pack_truncated": 0,
        }
        if self.maintenance_mode:
            fallback_reason = "RAG index is under maintenance"
            vector_results = []
        else:
            try:
                vector_results, relevance_hint, eval_result, rerank_success, score_type, hybrid_status, fts_exceptions, rerank_status, variants_dropped, exact_match_promoted, token_pack_stats = await self._execute_retrieval(
                    query_embeddings,
                    user_input,
                    vault_id,
                    effective_alpha=effective_alpha,
                    variants_dropped=variants_dropped,
                )
                logger.info(
                    "[query] _execute_retrieval returned: result_count=%d, first_3_distances=%s",
                    len(vector_results),
                    [r.get("_distance") for r in vector_results[:3]]
                    if vector_results
                    else "N/A",
                )
            except Exception as exc:
                fallback_reason = str(exc)
                vector_results = []
                rerank_success = None  # Default for fallback case
                rerank_status = "disabled"  # Default for fallback
                score_type = "distance"  # Default for fallback
                hybrid_status = "disabled"  # Default for fallback
                fts_exceptions = 0  # Default for fallback
                variants_dropped = []  # Safety net: reset on exception
                exact_match_promoted = False  # Default for fallback
                token_pack_stats = {
                    "token_pack_included": 0,
                    "token_pack_skipped": 0,
                    "token_pack_truncated": 0,
                }

        # Fetch indexed file IDs for atomic visibility filter (Issue #13)
        # Only chunks from fully-indexed files are returned — pending/processing files are hidden.
        indexed_file_ids: Optional[Set[str]] = None
        try:
            indexed_file_ids = await asyncio.to_thread(
                self._get_indexed_file_ids, vault_id
            )
        except Exception as _exc:
            logger.warning(
                "Failed to fetch indexed_file_ids (visibility filter disabled): %s", _exc
            )

        # Capture retrieval-phase trace stats before filtering.
        trace.fused_hits = len(vector_results)
        trace.fts_status = hybrid_status
        trace.fts_exceptions = fts_exceptions
        trace.rerank_status = rerank_status
        trace.variants_dropped = list(variants_dropped or [])
        trace.exact_match_promoted = exact_match_promoted
        trace.token_pack_included = token_pack_stats.get("token_pack_included", 0)
        trace.token_pack_skipped = token_pack_stats.get("token_pack_skipped", 0)
        trace.token_pack_truncated = token_pack_stats.get("token_pack_truncated", 0)

        # Filter relevant chunks using document retrieval service
        relevant_chunks = await self.document_retrieval.filter_relevant(
            vector_results,
            reranked=rerank_success if rerank_success is not None else False,
            indexed_file_ids=indexed_file_ids,
        )
        logger.info(
            "[query] After filter_relevant: relevant_chunk_count=%d",
            len(relevant_chunks),
        )
        trace.filtered_hits = len(relevant_chunks)

        # Context distillation: deduplicate overlapping chunks and optionally synthesize
        if settings.context_distillation_enabled and relevant_chunks:
            try:
                distiller = ContextDistiller(
                    self.embedding_service,
                    self.llm_client if settings.context_distillation_synthesis_enabled else None,
                )
                trace.distillation_before = len(relevant_chunks)
                relevant_chunks = await distiller.distill(
                    user_input, relevant_chunks, eval_result
                )
                trace.distillation_after = len(relevant_chunks)
                logger.info(
                    "[query] After context distillation: chunk_count=%d",
                    len(relevant_chunks),
                )
            except Exception as exc:
                logger.warning("Context distillation failed, continuing: %s", exc)

        # Parent window expansion: deliver parent context to LLM (Issue #12)
        # Reads pre-computed parent_window_text from chunk metadata and assigns it to
        # source.parent_window_text; prompt_builder renders it with [[MATCH:]] markers.
        if settings.parent_retrieval_enabled and relevant_chunks:
            relevant_chunks = self._expand_parent_windows(relevant_chunks)
            trace.parent_windows_expanded = sum(
                1 for c in relevant_chunks if getattr(c, "parent_window_text", None)
            )

        # Check if distance filtering removed all results (no_match)
        if not relevant_chunks and self.document_retrieval.no_match:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Distance filtering: NO_MATCH for query '%s'", user_input)
            relevance_hint = "Note: The retrieved documents may not be directly relevant to your query. The system found no chunks within the relevance threshold."

        # Supersession check: warn if retrieved files have newer versions
        if relevant_chunks:
            supersession_warning = await self._check_supersession(relevant_chunks)
            if supersession_warning:
                if relevance_hint:
                    relevance_hint = supersession_warning + "\n" + relevance_hint
                else:
                    relevance_hint = supersession_warning

        if fallback_reason:
            logger.warning("Vector search fallback triggered: %s", fallback_reason)
            logger.debug("[query] Yielding 'fallback' chunk")
            yield {
                "type": "fallback",
                "reason": fallback_reason,
                "results": [],
                "total": 0,
                "fallback": True,
            }

        # Search memories (hybrid: FTS + dense + RRF, with FTS fallback).
        # Gated by ``memory_retrieval_enabled`` so operators can disable
        # the path during incident response without redeploying.
        memories = []
        if settings.memory_retrieval_enabled:
            try:
                candidates = await asyncio.to_thread(
                    self.memory_store.search_memories,
                    user_input,
                    settings.memory_retrieval_top_k,
                    vault_id=vault_id,
                )
                # Apply context_top_k cap after relevance filtering so prompt context
                # stays bounded even when top_k is large.
                memories = candidates[: settings.memory_context_top_k]
                logger.info(
                    "[query] Memory: %d candidates → %d after context_top_k cap",
                    len(candidates),
                    len(memories),
                )
            except Exception as exc:
                logger.error("Memory search failed: %s", exc)
                memories = []

        # Build messages using prompt builder service
        messages = self.prompt_builder.build_messages(
            user_input, chat_history, relevant_chunks, memories, relevance_hint
        )

        # Stream or non-stream LLM response. Capture the assembled
        # content so citation labels can be parsed for the trace.
        assembled_response: List[str] = []
        if stream:
            async for chunk in self._stream_llm_response(messages):
                chunk_type = chunk.get("type", "unknown")
                logger.debug("[query] Yielding '%s' chunk (stream)", chunk_type)
                if chunk_type == "content":
                    assembled_response.append(chunk.get("content", ""))
                yield chunk
        else:
            async for chunk in self._get_llm_response(messages):
                chunk_type = chunk.get("type", "unknown")
                logger.debug("[query] Yielding '%s' chunk (non-stream)", chunk_type)
                if chunk_type == "content":
                    assembled_response.append(chunk.get("content", ""))
                yield chunk

        # Citation parsing for the trace (does not modify content; the
        # chat route does the user-visible repair).
        full_response = "".join(assembled_response)
        cited_sources, cited_memories = parse_citations(full_response)
        trace.cited_sources = cited_sources
        trace.cited_memories = cited_memories

        # Yield done message with sources. Pass cited_labels so that
        # memories_used contains only memories the assistant actually cited.
        done_msg = self._build_done_message(
            relevant_chunks,
            memories,
            score_type,
            hybrid_status,
            fts_exceptions,
            rerank_status,
            variants_dropped,
            exact_match_promoted,
            token_pack_stats,
            cited_labels=set(cited_memories),
        )
        # Populate final-source labels on the trace for evaluation tooling.
        trace.final_sources = [
            s.get("source_label", "") for s in done_msg.get("sources", []) if s.get("source_label")
        ]
        trace.final_memories = [
            m.get("memory_label", "") for m in done_msg.get("memories_used", []) if m.get("memory_label")
        ]
        # Run citation validation against the assembled response.
        try:
            validation = repair_against_sources_and_memories(
                full_response,
                done_msg.get("sources", []),
                done_msg.get("memories_used", []),
            )
            trace.invalid_citations = list(validation.invalid_citations)
            trace.answer_supported = (
                validation.has_any_citation or not validation.has_evidence
            ) and not validation.uncited_factual_warning
        except Exception:  # pragma: no cover — defensive
            trace.invalid_citations = []
            trace.answer_supported = None

        # Always log the trace; embed in done payload only when the operator
        # opts in via ``settings.rag_trace_in_response``.
        trace.log()
        if settings.rag_trace_in_response:
            done_msg["trace"] = trace.to_dict()

        logger.info(
            "[query] Yielding 'done': sources_count=%d, memories_used=%d",
            len(done_msg.get("sources", [])),
            len(done_msg.get("memories_used", [])),
        )
        yield done_msg

    async def _execute_retrieval(
        self,
        query_embeddings: List[Tuple[str, List[float]]],
        user_input: str,
        vault_id: Optional[int],
        effective_alpha: float = 0.6,
        variants_dropped: List[str] = None,
    ) -> tuple[List[Dict[str, Any]], Optional[str], str, Optional[bool], str, str, int, str, List[str], bool, Dict[str, int]]:
        """Execute vector search and retrieval evaluation.

        Args:
            query_embeddings: List of (variant_type, embedding) tuples to search
            user_input: Original user query
            vault_id: Optional vault ID to filter by
            effective_alpha: Hybrid search alpha weight
            variants_dropped: List of variant types that failed embedding (e.g., step_back, hyde)

        Returns:
            Tuple of (vector_results, relevance_hint, eval_result, rerank_success, score_type,
            hybrid_status, fts_exceptions, rerank_status, variants_dropped, exact_match_promoted,
            token_pack_stats)
        """
        logger.info(
            "[_execute_retrieval] ENTER: vault_id=%s, top_k=%s, query_embeddings=%d",
            vault_id,
            self.retrieval_top_k,
            len(query_embeddings),
        )
        # Ensure variants_dropped is always a list (never None)
        if variants_dropped is None:
            variants_dropped = []
        eval_result = "CONFIDENT"
        rerank_success: Optional[bool] = None
        fts_exceptions = 0  # Initialize before try in case get_fts_exceptions() raises
        final_relevance_hint: Optional[str] = None  # Initialize before try block

        # Phase 1: Search phase - original query failures propagate immediately
        vector_results = []
        try:
            fetch_k = (
                self.initial_retrieval_top_k
                if self.reranking_enabled
                else self.retrieval_top_k
            )
            top_k_value = fetch_k if fetch_k is not None else self.retrieval_top_k

            # Search with all query embeddings concurrently and fuse results
            _top_k = int(top_k_value) if top_k_value is not None else 10
            _vault = str(vault_id) if vault_id is not None else None
            search_tasks = [
                self.vector_store.search(
                    embedding_tuple[1],  # Extract embedding from (variant_type, embedding) tuple
                    _top_k,
                    vault_id=_vault,
                    query_text=user_input,
                    hybrid=self.hybrid_search_enabled,
                    hybrid_alpha=effective_alpha,
                )
                for embedding_tuple in query_embeddings
            ]
            gather_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            all_results = []
            for i, result in enumerate(gather_results):
                variant_type = query_embeddings[i][0] if i < len(query_embeddings) else f"variant_{i}"
                if isinstance(result, BaseException):
                    # ORIGINAL QUERY FAILURE: propagate error immediately
                    if variant_type == 'original':
                        raise RAGEngineError(f"Original query vector search failed: {result}") from result

                    # Paraphrase/step_back/hyde failure: log and track
                    logger.warning(
                        "[_execute_retrieval] vector search variant=%d (%s) failed: %s",
                        i, variant_type, result,
                    )
                    if variant_type not in variants_dropped:
                        variants_dropped.append(variant_type)
                    all_results.append([])  # Degrade gracefully — use empty result for failed variant
                else:
                    all_results.append(result)
                    logger.debug(
                        "[_execute_retrieval] vector_store.search() variant=%d (%s) returned %d results",
                        i,
                        variant_type,
                        len(result),
                    )

            # Compute recency scores for tiebreaking in multi-query fusion
            recency_scores: Optional[Dict[str, float]] = None
            if settings.retrieval_recency_weight > 0.0 and len(all_results) > 1:
                dates: Dict[str, float] = {}
                for result_list in all_results:
                    for record in result_list:
                        uid = record.get("id", "")
                        if not uid:
                            continue
                        metadata = self._normalize_metadata(record.get("metadata", {}))
                        proc_at = metadata.get("processed_at") or record.get(
                            "processed_at"
                        )
                        if proc_at:
                            try:
                                dates[uid] = datetime.fromisoformat(
                                    str(proc_at)
                                ).timestamp()
                            except (ValueError, TypeError):
                                pass
                if len(dates) > 1:
                    min_ts = min(dates.values())
                    max_ts = max(dates.values())
                    span = max_ts - min_ts or 1.0
                    recency_scores = {
                        uid: (ts - min_ts) / span for uid, ts in dates.items()
                    }

            # Capture top-1 from original query for exact-match promotion (before fusion modifies ordering)
            original_top1_id = None
            exact_match_promoted = False
            if all_results and all_results[0]:
                original_top1_id = all_results[0][0].get("id") if all_results[0] else None

            # Fuse results from all query variants using RRF with configurable k and per-arm weights
            if len(all_results) > 1:
                # Build per-arm weights based on variant types
                # query_embeddings is a list of (variant_type, embedding) tuples
                if not settings.rrf_legacy_mode:
                    weight_map = {
                        'original': settings.rrf_weight_original,
                        'step_back': settings.rrf_weight_stepback,
                        'hyde': settings.rrf_weight_hyde,
                    }
                    variant_weights = []
                    filtered_results = []
                    for i, result_list in enumerate(all_results):
                        variant_type = query_embeddings[i][0] if i < len(query_embeddings) else 'original'
                        w = weight_map.get(variant_type, settings.rrf_weight_original)
                        if w > 0.0:
                            variant_weights.append(w)
                            filtered_results.append(result_list)
                    fusion_k = settings.multi_query_rrf_k
                else:
                    # Legacy mode: k=60, uniform weights, no filtering
                    variant_weights = None
                    filtered_results = all_results
                    fusion_k = 60

                vector_results = rrf_fuse(
                    filtered_results,
                    k=fusion_k,
                    limit=fetch_k,
                    weights=variant_weights,
                    recency_scores=recency_scores,
                    recency_weight=settings.retrieval_recency_weight,
                )
                logger.info(
                    "Fused results from %d query variants: %d results",
                    len(all_results),
                    len(vector_results),
                )

                # Exact-match promotion: ensure original query's top-1 dense result
                # is not completely demoted out of top-5 by variant fusion math
                exact_match_promoted = False
                if (
                    settings.exact_match_promote
                    and not settings.rrf_legacy_mode
                    and original_top1_id is not None
                    and len(vector_results) >= 5
                ):
                    top5_ids = {r.get("id") for r in vector_results[:5]}
                    if original_top1_id not in top5_ids:
                        # Find the original top-1 in fused results
                        promote_idx = None
                        for idx, r in enumerate(vector_results):
                            if r.get("id") == original_top1_id:
                                promote_idx = idx
                                break
                        if promote_idx is not None:
                            # Promote to rank 5 (index 4) — a nudge, not a crown.
                            # Exact string match does not override semantic ranking;
                            # rank 5 keeps it in the Primary Evidence window.
                            promoted_record = vector_results.pop(promote_idx)
                            vector_results.insert(4, promoted_record)
                            exact_match_promoted = True
                            logger.info(
                                "Exact-match promotion: moved original top-1 from position %d to rank 5",
                                promote_idx,
                            )
            else:
                vector_results = all_results[0] if all_results else []
                exact_match_promoted = False

            # Log vector search results
            logger.info(
                "Vector search: vault_id=%s, top_k=%d, results=%d, distances=%s",
                vault_id,
                top_k_value,
                len(vector_results),
                [r.get("_distance") for r in vector_results[:3]]
                if vector_results
                else "N/A",
            )

            # Phase 1b: Reranking (if enabled) - also part of search phase
            if self.reranking_enabled and self.reranking_service and vector_results:
                try:
                    reranked_chunks, rerank_success = await self.reranking_service.rerank(
                        query=user_input,
                        chunks=vector_results,
                        top_n=self.reranker_top_n,
                    )
                    if reranked_chunks:
                        vector_results = reranked_chunks
                    logger.info(
                        "[_execute_retrieval] After reranking: result_count=%d",
                        len(vector_results),
                    )
                except Exception as e:
                    logger.warning("Reranking failed, using original results: %s", e)
                    # rerank_success remains None (unattempted due to exception)

            # Determine final rerank_success value
            # rerank_success is set inside the reranking block (from unpacking)
            # or remains None if reranking wasn't attempted
            if not self.reranking_enabled:
                # Reranking is globally disabled
                rerank_success = None
            elif rerank_success is None:
                # We attempted reranking but exception occurred, so no success value from service
                rerank_success = None
            else:
                # rerank_success is the boolean from the service (True=succeeded, False=fallback)
                # Keep the value as-is
                pass
            logger.debug(
                "[_execute_retrieval] Rerank success: %s",
                rerank_success,
            )

            # Compute score_type from actual rerank_success (not config flag)
            if rerank_success:
                score_type = "rerank"
            else:
                score_type = "distance"

            # Compute hybrid_status from _fts_status in results
            if not self.hybrid_search_enabled:
                hybrid_status = "disabled"
            else:
                # Check if any result has _fts_status='ok'
                has_fts_ok = any(
                    r.get("_fts_status") == "ok" for r in vector_results
                )
                hybrid_status = "both" if has_fts_ok else "dense_only"

            # Get FTS exceptions (call ONCE per query — resets counter)
            fts_exceptions = self.vector_store.get_fts_exceptions()

            # Compute rerank_status string from rerank_success boolean
            if rerank_success is True:
                rerank_status = "ok"
            elif rerank_success is False:
                rerank_status = "fallback"
            else:
                rerank_status = "disabled"

        except RAGEngineError:
            # Re-raise original query search failures immediately
            raise
        except Exception as search_error:
            # Handle paraphrase/search task failures - log and return empty results
            logger.warning(
                "[_execute_retrieval] Search phase exception: %s, using partial results",
                search_error,
            )
            vector_results = []
            rerank_success = None
            score_type = "distance"
            hybrid_status = "disabled"
            fts_exceptions = 0
            rerank_status = "disabled"
            exact_match_promoted = False

        # Phase 2: Evaluation/post-processing phase (only reached if search succeeds with results)
        token_pack_stats: Dict[str, int] = {
            "token_pack_included": 0,
            "token_pack_skipped": 0,
            "token_pack_truncated": 0,
        }
        if vector_results:
            try:
                # Token packing (only if we have results)
                if settings.context_max_tokens > 0:
                    temp_sources = [
                        RAGSource(
                            text=r.get("text", ""),
                            file_id=str(r.get("file_id", "")),
                            score=r.get("_distance", 0.0),
                            metadata=r.get("metadata", {}),
                        )
                        for r in vector_results
                    ]
                    packed_sources, token_pack_stats = self._pack_context_by_token_budget(
                        temp_sources, settings.context_max_tokens
                    )
                    # Rebuild vector_results in packed_sources ORDER (preserves reranker ranking).
                    # Use (file_id, text) composite key — more unique than text alone.
                    _key_to_result: Dict[tuple, Any] = {}
                    for r in vector_results:
                        k = (str(r.get("file_id", "")), r.get("text", ""))
                        if k not in _key_to_result:  # first-seen wins (reranker order)
                            _key_to_result[k] = r
                    vector_results = [
                        _key_to_result[(s.file_id, s.text)]
                        for s in packed_sources
                        if (s.file_id, s.text) in _key_to_result
                    ]
                    logger.info(
                        "Token packing: %d results → %d results (budget=%d tokens, "
                        "included=%d, skipped=%d, truncated=%d)",
                        len(temp_sources),
                        len(packed_sources),
                        settings.context_max_tokens,
                        token_pack_stats["token_pack_included"],
                        token_pack_stats["token_pack_skipped"],
                        token_pack_stats["token_pack_truncated"],
                    )

                # Final limit to retrieval_top_k
                vector_results = vector_results[: self.retrieval_top_k]

                # Retrieval evaluation (CRAG-style self-evaluation)
                relevance_hint_eval: Optional[str] = None
                if settings.retrieval_evaluation_enabled and self.llm_client is not None:
                    try:
                        if self._retrieval_evaluator is None:
                            self._retrieval_evaluator = RetrievalEvaluator(self.llm_client)
                        eval_result = await self._retrieval_evaluator.evaluate(
                            user_input, vector_results
                        )
                        if eval_result == "NO_MATCH":
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "Retrieval evaluation: NO_MATCH for query '%s'",
                                    user_input,
                                )
                            relevance_hint_eval = "Note: The retrieved documents may not be directly relevant to your query."
                        elif eval_result == "AMBIGUOUS":
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(
                                    "Retrieval evaluation: AMBIGUOUS for query '%s'",
                                    user_input,
                                )
                    except Exception as e:
                        logger.warning("Retrieval evaluation failed: %s", e)
                # Final relevance_hint from evaluation, or None
                final_relevance_hint = relevance_hint_eval

            except Exception as eval_error:
                logger.warning("Post-retrieval evaluation failed: %s", eval_error)
                # Continue with original results if evaluation fails
                # NOTE: Do NOT reset exact_match_promoted here — if promotion already
                # succeeded (modifying vector_results ordering), the flag must remain True.

        # Compute score_type from actual rerank_success (not config flag)
        if rerank_success:
            score_type = "rerank"
        else:
            score_type = "distance"

        # Compute hybrid_status from _fts_status in results
        if not self.hybrid_search_enabled:
            hybrid_status = "disabled"
        else:
            # Check if any result has _fts_status='ok'
            has_fts_ok = any(
                r.get("_fts_status") == "ok" for r in vector_results
            )
            hybrid_status = "both" if has_fts_ok else "dense_only"

        # Compute rerank_status string from rerank_success boolean
        if rerank_success is True:
            rerank_status = "ok"
        elif rerank_success is False:
            rerank_status = "fallback"
        else:
            rerank_status = "disabled"

        return vector_results, final_relevance_hint, eval_result, rerank_success, score_type, hybrid_status, fts_exceptions, rerank_status, variants_dropped, exact_match_promoted, token_pack_stats

    async def _stream_llm_response(
        self,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream LLM response chunks.

        Args:
            messages: List of message dictionaries

        Yields:
            Response chunks as dictionaries
        """
        try:
            async for chunk in self.llm_client.chat_completion_stream(messages):
                yield {"type": "content", "content": chunk}
        except LLMError as exc:
            logger.error("[_stream_llm_response] LLMError: %s", exc)
            yield {"type": "error", "message": str(exc), "code": "LLM_ERROR"}

    async def _get_llm_response(
        self,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Get non-streaming LLM response.

        Args:
            messages: List of message dictionaries

        Yields:
            Response content dictionary

        Raises:
            RAGEngineError: If LLM call fails
        """
        try:
            content = await self.llm_client.chat_completion(messages)
            yield {"type": "content", "content": content}
        except LLMError as exc:
            raise RAGEngineError(f"LLM chat failed: {exc}") from exc

    def _build_done_message(
        self,
        relevant_chunks: List[RAGSource],
        memories: List[Any],
        score_type: str,
        hybrid_status: str,
        fts_exceptions: int,
        rerank_status: str,
        variants_dropped: List[str] = None,
        exact_match_promoted: bool = False,
        token_pack_stats: Optional[Dict[str, int]] = None,
        cited_labels: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Build the final done message with sources.

        Args:
            relevant_chunks: Filtered relevant chunks
            memories: Retrieved memories
            score_type: Score type used ("rerank" or "distance")
            hybrid_status: Hybrid search status ("disabled", "dense_only", or "both")
            fts_exceptions: Number of FTS exceptions encountered
            rerank_status: Reranking status ("ok", "fallback", or "disabled")
            variants_dropped: Query variant types that failed embedding/search
            exact_match_promoted: Whether exact-match promotion was triggered
            token_pack_stats: Token packing counters (included, skipped, truncated)

        Returns:
            Done message dictionary
        """
        _pack_stats = token_pack_stats or {
            "token_pack_included": 0,
            "token_pack_skipped": 0,
            "token_pack_truncated": 0,
        }
        retrieval_debug: Dict[str, Any] = {
            "max_distance_threshold": self.max_distance_threshold,
            "vector_metric": self.vector_metric,
            "retrieval_top_k": self.retrieval_top_k,
            "hybrid_status": hybrid_status,
            "fts_exceptions": fts_exceptions,
            "rerank_status": rerank_status,
            "variants_dropped": variants_dropped or [],
            "exact_match_promoted": exact_match_promoted if settings.exact_match_promote else None,
            "token_pack_included": _pack_stats["token_pack_included"],
            "token_pack_skipped": _pack_stats["token_pack_skipped"],
            "token_pack_truncated": _pack_stats["token_pack_truncated"],
        }

        # Split into primary and supporting (same split as prompt builder)
        primary_count = calculate_primary_count(len(relevant_chunks))

        sources = []
        for idx, chunk in enumerate(relevant_chunks):
            source_meta = self.document_retrieval.to_source_metadata(
                chunk, source_index=idx + 1
            )
            source_meta["evidence_type"] = (
                "primary" if idx < primary_count else "supporting"
            )
            sources.append(source_meta)

        # Build structured memories_used list with stable [M#] labels.
        # Memories are not document sources — they get their own label space.
        # Only memories whose label was actually cited in the response are
        # included; injected-but-uncited candidates are excluded so that
        # memories_used means "evidence the assistant used," not "candidates
        # that were available." Original label numbers are preserved to match
        # the [M#] references in the response text.
        memories_used: List[Dict[str, Any]] = []
        for idx, mem in enumerate(memories):
            label = f"M{idx + 1}"
            if cited_labels is not None and label not in cited_labels:
                continue
            memories_used.append(
                {
                    "id": str(getattr(mem, "id", "")) or label,
                    "memory_label": label,
                    "content": getattr(mem, "content", "") or "",
                    "category": getattr(mem, "category", None),
                    "tags": getattr(mem, "tags", None),
                    "source": getattr(mem, "source", None),
                    "vault_id": getattr(mem, "vault_id", None),
                    "score": getattr(mem, "score", None),
                    "score_type": getattr(mem, "score_type", None) or "fts",
                    "created_at": getattr(mem, "created_at", None),
                    "updated_at": getattr(mem, "updated_at", None),
                }
            )

        return {
            "type": "done",
            "sources": sources,
            "memories_used": memories_used,
            "retrieval_debug": retrieval_debug,
            "score_type": score_type,
        }

    def _ensure_services(self) -> None:
        """Ensure extracted services are initialized.

        This handles edge cases where __init__ was patched or skipped (e.g., in tests).
        """
        if not hasattr(self, "document_retrieval") or self.document_retrieval is None:
            self.document_retrieval = DocumentRetrievalService(
                vector_store=getattr(self, "vector_store", None),
                max_distance_threshold=getattr(self, "max_distance_threshold", None),
                retrieval_top_k=getattr(self, "retrieval_top_k", None),
                retrieval_window=getattr(self, "retrieval_window", None),
            )
        if not hasattr(self, "prompt_builder") or self.prompt_builder is None:
            self.prompt_builder = PromptBuilderService()

    # Backward compatibility methods - delegate to document_retrieval service
    async def _filter_relevant(
        self, results: List[Dict[str, Any]], top_k: Optional[int] = None
    ) -> List[RAGSource]:
        """Filter retrieved documents by relevance (backward compatibility).

        Syncs threshold settings from engine to document_retrieval service
        to support tests that modify engine settings after initialization.
        """
        self._ensure_services()
        # Sync settings from engine to service
        self.document_retrieval.max_distance_threshold = getattr(
            self, "max_distance_threshold", None
        )
        self.document_retrieval.relevance_threshold = getattr(
            self, "relevance_threshold", None
        )
        self.document_retrieval.retrieval_top_k = getattr(self, "retrieval_top_k", None)
        self.document_retrieval.retrieval_window = getattr(self, "retrieval_window", 0)
        return await self.document_retrieval.filter_relevant(results, top_k)

    def _pack_context_by_token_budget(
        self, chunks: List[RAGSource], max_tokens: int = 6000
    ) -> Tuple[List[RAGSource], Dict[str, int]]:
        """
        Pack context chunks by token budget, respecting max token limit.

        Strategy is controlled by settings.token_pack_strategy:

        - ``reserved_best_fit`` (default): Always includes the top
          ``min(3, len(chunks))`` chunks regardless of budget (never skipped).
          For remaining chunks, uses best-fit: a chunk that doesn't fit is
          *skipped* but evaluation continues for smaller subsequent chunks
          (no early ``break``).  Oversize reserved chunks are tracked in
          ``token_pack_truncated`` — they inflate the running total but are
          never dropped.

        - ``greedy`` (legacy): First-fit scan; stops entirely on first overflow
          (original behavior, kept for rollback).

        Args:
            chunks: List of RAGSource chunks to pack (in rank order).
            max_tokens: Approximate token budget (default 6000).

        Returns:
            Tuple of (packed_chunks, debug_stats) where debug_stats contains:
              - token_pack_included: count of chunks included
              - token_pack_skipped:  count of rank-4+ chunks that didn't fit
              - token_pack_truncated: count of reserved top-3 chunks whose
                                      token estimate exceeded the remaining budget
                                      (included anyway; no actual text modification)
        """
        _empty_stats: Dict[str, int] = {
            "token_pack_included": 0,
            "token_pack_skipped": 0,
            "token_pack_truncated": 0,
        }
        if not chunks:
            return [], _empty_stats

        strategy = settings.token_pack_strategy

        if strategy == "greedy":
            packed, token_count = [], 0
            for chunk in chunks:
                # ~3.5 chars/token for English; overestimates to prevent overflow
                chunk_tokens = max(1, int(len(chunk.text) / 3.5))
                if token_count + chunk_tokens > max_tokens and packed:
                    break
                packed.append(chunk)
                token_count += chunk_tokens
            stats: Dict[str, int] = {
                "token_pack_included": len(packed),
                "token_pack_skipped": max(0, len(chunks) - len(packed)),
                "token_pack_truncated": 0,
            }
            return packed, stats

        # reserved_best_fit (default)
        n_reserved = min(3, len(chunks))
        reserved_chunks = chunks[:n_reserved]
        remaining_chunks = chunks[n_reserved:]

        packed = []
        token_count = 0
        truncated = 0

        # Phase 1: reserved top-N — always include, even if over budget.
        # Track when a reserved chunk pushes past the remaining budget.
        for chunk in reserved_chunks:
            chunk_tokens = max(1, int(len(chunk.text) / 3.5))
            if token_count + chunk_tokens > max_tokens and packed:
                # Over budget for this reserved slot — include anyway, mark truncated.
                # (The LLM context window provides the final safety net.)
                truncated += 1
            packed.append(chunk)
            token_count += chunk_tokens

        # Phase 2: best-fit for rank 4+ — skip overflows but keep evaluating.
        skipped = 0
        for chunk in remaining_chunks:
            chunk_tokens = max(1, int(len(chunk.text) / 3.5))
            if token_count + chunk_tokens <= max_tokens:
                packed.append(chunk)
                token_count += chunk_tokens
            else:
                skipped += 1
                # Intentionally no ``break``: continue checking smaller chunks.

        stats = {
            "token_pack_included": len(packed),
            "token_pack_skipped": skipped,
            "token_pack_truncated": truncated,
        }
        return packed, stats

    async def _check_supersession(self, sources: List[RAGSource]) -> Optional[str]:
        """Query SQLite to check if any retrieved files have been superseded by newer versions.

        Feature-flag gated by files table schema — only runs if supersedes_file_id column exists.
        """
        file_ids = list({src.file_id for src in sources if src.file_id})
        if not file_ids:
            return None
        try:

            def _query() -> list:
                pool = _get_pool()
                with pool.connection() as conn:
                    # Check if supersedes_file_id column exists in files table
                    cursor = conn.execute("PRAGMA table_info(files)")
                    columns = {row[1] for row in cursor.fetchall()}
                    if "supersedes_file_id" not in columns:
                        logger.debug(
                            "Supersession check skipped: supersedes_file_id column not in files table"
                        )
                        return []

                    placeholders = ",".join("?" * len(file_ids))
                    sql = (
                        f"SELECT file_name FROM files "
                        f"WHERE supersedes_file_id IN ({placeholders}) AND status='indexed'"
                    )
                    rows = conn.execute(sql, file_ids).fetchall()
                    return rows

            rows = await asyncio.to_thread(_query)
            if rows:
                newer_names = [r[0] for r in rows]
                logger.warning(
                    "Supersession warning: retrieved file_ids %s have been superseded by %s",
                    file_ids,
                    newer_names,
                )
                return (
                    "\u26a0\ufe0f Note: One or more retrieved documents may have been superseded by a "
                    "newer version in the knowledge base. Verify currency of information where critical."
                )
        except Exception as exc:
            logger.warning("Supersession check failed (suppressed): %s", exc)
        return None

    def _get_indexed_file_ids(self, vault_id: Optional[int]) -> Optional[Set[str]]:
        """Return the set of file IDs with status='indexed' from SQLite (Issue #13).

        Used to filter out chunks belonging to files still being ingested (pending /
        processing) so that partial-ingest state is never visible to the LLM.

        Args:
            vault_id: If provided, restrict to files in this vault.

        Returns:
            Set of str file IDs, or None if the lookup fails (caller falls back to
            no filtering rather than blocking the query).
        """
        try:
            pool = _get_pool()
            conn = pool.get_connection()
            try:
                if vault_id is not None:
                    cursor = conn.execute(
                        "SELECT id FROM files WHERE status='indexed' AND vault_id=?",
                        (vault_id,),
                    )
                else:
                    cursor = conn.execute("SELECT id FROM files WHERE status='indexed'")
                rows = cursor.fetchall()
                return {str(row["id"]) for row in rows}
            finally:
                pool.release_connection(conn)
        except Exception as exc:
            logger.debug("_get_indexed_file_ids failed: %s", exc)
            return None

    def _expand_parent_windows(self, sources: List[RAGSource]) -> List[RAGSource]:
        """Populate parent_window_text on each source when available (Issue #12).

        Reads the pre-computed ``parent_window_text`` from chunk metadata (stored
        at ingest time) and assigns it to ``source.parent_window_text``.  The
        prompt_builder renders this wider context with ``[[MATCH: …]]`` markers
        around the original small-chunk text so the LLM sees both the precise match
        and its surrounding context.

        Only active when ``PARENT_RETRIEVAL_ENABLED=True``.  If a chunk has no
        stored parent window (legacy chunks, spreadsheets, schema files), the field
        remains None and the chunk's own text is used as-is.
        """
        expanded = 0
        for source in sources:
            pw_text = source.metadata.get("parent_window_text")
            if pw_text:
                source.parent_window_text = pw_text
                expanded += 1

        if expanded:
            logger.debug(
                "_expand_parent_windows: expanded %d/%d chunks with parent window context",
                expanded,
                len(sources),
            )
        return sources

    async def _expand_window(self, sources: List[RAGSource]) -> List[RAGSource]:
        """Expand search results by fetching adjacent chunks (backward compatibility).

        Syncs window settings from engine to document_retrieval service
        to support tests that modify engine settings after initialization.
        """
        self._ensure_services()
        self.document_retrieval.retrieval_window = getattr(self, "retrieval_window", 0)
        self.document_retrieval.retrieval_top_k = getattr(self, "retrieval_top_k", None)
        return await self.document_retrieval.expand_window(sources)

    def _normalize_metadata(self, metadata: Any) -> Dict[str, Any]:
        """Normalize metadata (backward compatibility)."""
        self._ensure_services()
        return self.document_retrieval._normalize_metadata(metadata)

    # Backward compatibility methods - delegate to prompt_builder service
    def _build_system_prompt(self) -> str:
        """Build system prompt (backward compatibility)."""
        self._ensure_services()
        return self.prompt_builder.build_system_prompt()

    def _build_messages(
        self,
        user_input: str,
        chat_history: List[Dict[str, Any]],
        chunks: List[RAGSource],
        memories: List[Any],
        relevance_hint: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build messages for LLM (backward compatibility)."""
        self._ensure_services()
        return self.prompt_builder.build_messages(
            user_input, chat_history, chunks, memories, relevance_hint
        )

    def _format_chunk(self, chunk: RAGSource) -> str:
        """Format chunk for context (backward compatibility)."""
        self._ensure_services()
        return self.prompt_builder.format_chunk(chunk)

    def _source_metadata(self, chunk: RAGSource) -> Dict[str, Any]:
        """Convert chunk to source metadata (backward compatibility)."""
        self._ensure_services()
        return self.document_retrieval.to_source_metadata(chunk)
