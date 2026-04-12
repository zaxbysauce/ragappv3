"""Retrieval-augmented generation engine orchestration."""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import settings
from app.services.document_retrieval import DocumentRetrievalService, RAGSource
from app.services.embeddings import EmbeddingService, EmbeddingError
from app.services.llm_client import LLMClient, LLMError
from app.services.memory_store import MemoryStore
from app.services.prompt_builder import PromptBuilderService, calculate_primary_count
from app.services.query_transformer import QueryTransformer
from app.services.context_distiller import ContextDistiller
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
        transformed_queries: List[str] = [user_input]
        if settings.query_transformation_enabled and self.llm_client is not None:
            try:
                if self._query_transformer is None:
                    self._query_transformer = QueryTransformer(self.llm_client)
                transformed_queries = await self._query_transformer.transform(
                    user_input
                )
                if len(transformed_queries) > 1:
                    logger.info(
                        "Query transformation: original='%s', step_back='%s'",
                        transformed_queries[0],
                        transformed_queries[1],
                    )
            except Exception as e:
                logger.warning(
                    "Query transformation failed (%s): %s, using original query only", type(e).__name__, e
                )
                transformed_queries = [user_input]

        logger.debug("[query] transformed_queries=%s", transformed_queries)

        # Embed all transformed queries concurrently
        query_embeddings: List[List[float]] = []
        embed_results = await asyncio.gather(
            *[self.embedding_service.embed_single(q) for q in transformed_queries],
            return_exceptions=True,
        )
        for i, result in enumerate(embed_results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Query embedding failure [%d/%d]: query='%.50s', error=%s",
                    i + 1, len(transformed_queries), transformed_queries[i], result,
                )
            else:
                query_embeddings.append(result)

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
            len(query_embeddings[0]) if query_embeddings else "N/A",
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
        if self.maintenance_mode:
            fallback_reason = "RAG index is under maintenance"
            vector_results = []
        else:
            try:
                vector_results, relevance_hint, eval_result = await self._execute_retrieval(
                    query_embeddings,
                    user_input,
                    vault_id,
                    effective_alpha=effective_alpha,
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

        # Filter relevant chunks using document retrieval service
        relevant_chunks = await self.document_retrieval.filter_relevant(vector_results)
        logger.info(
            "[query] After filter_relevant: relevant_chunk_count=%d",
            len(relevant_chunks),
        )

        # Context distillation: deduplicate overlapping chunks and optionally synthesize
        if settings.context_distillation_enabled and relevant_chunks:
            try:
                distiller = ContextDistiller(
                    self.embedding_service,
                    self.llm_client if settings.context_distillation_synthesis_enabled else None,
                )
                relevant_chunks = await distiller.distill(
                    user_input, relevant_chunks, eval_result
                )
                logger.info(
                    "[query] After context distillation: chunk_count=%d",
                    len(relevant_chunks),
                )
            except Exception as exc:
                logger.warning("Context distillation failed, continuing: %s", exc)

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

        # Search memories
        try:
            memories = await asyncio.to_thread(
                self.memory_store.search_memories,
                user_input,
                settings.retrieval_top_k,
                vault_id=vault_id,
            )
        except Exception as exc:
            logger.error("Memory search failed: %s", exc)
            memories = []

        # Build messages using prompt builder service
        messages = self.prompt_builder.build_messages(
            user_input, chat_history, relevant_chunks, memories, relevance_hint
        )

        # Stream or non-stream LLM response
        if stream:
            async for chunk in self._stream_llm_response(messages):
                chunk_type = chunk.get("type", "unknown")
                logger.debug("[query] Yielding '%s' chunk (stream)", chunk_type)
                yield chunk
        else:
            async for chunk in self._get_llm_response(messages):
                chunk_type = chunk.get("type", "unknown")
                logger.debug("[query] Yielding '%s' chunk (non-stream)", chunk_type)
                yield chunk

        # Yield done message with sources
        done_msg = self._build_done_message(relevant_chunks, memories)
        logger.info(
            "[query] Yielding 'done': sources_count=%d, memories_used=%d",
            len(done_msg.get("sources", [])),
            len(done_msg.get("memories_used", [])),
        )
        yield done_msg

    async def _execute_retrieval(
        self,
        query_embeddings: List[List[float]],
        user_input: str,
        vault_id: Optional[int],
        effective_alpha: float = 0.6,
    ) -> tuple[List[Dict[str, Any]], Optional[str], str]:
        """Execute vector search and retrieval evaluation.

        Args:
            query_embeddings: List of query embeddings to search
            user_input: Original user query
            vault_id: Optional vault ID to filter by

        Returns:
            Tuple of (vector_results, relevance_hint, eval_result)
        """
        logger.info(
            "[_execute_retrieval] ENTER: vault_id=%s, top_k=%s, query_embeddings=%d",
            vault_id,
            self.retrieval_top_k,
            len(query_embeddings),
        )
        eval_result = "CONFIDENT"
        try:
            # Stage 1: Initial retrieval
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
                    embedding,
                    _top_k,
                    vault_id=_vault,
                    query_text=user_input,
                    hybrid=self.hybrid_search_enabled,
                    hybrid_alpha=effective_alpha,
                )
                for i, embedding in enumerate(query_embeddings)
            ]
            gather_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            all_results = []
            for i, result in enumerate(gather_results):
                if isinstance(result, BaseException):
                    logger.warning(
                        "[_execute_retrieval] vector search variant=%d failed: %s",
                        i, result,
                    )
                    all_results.append([])  # Degrade gracefully — use empty result for failed variant
                else:
                    all_results.append(result)
                    logger.debug(
                        "[_execute_retrieval] vector_store.search() variant=%d returned %d results",
                        i,
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

            # Fuse results from all query variants using RRF
            if len(all_results) > 1:
                vector_results = rrf_fuse(
                    all_results,
                    k=60,
                    limit=fetch_k,
                    recency_scores=recency_scores,
                    recency_weight=settings.retrieval_recency_weight,
                )
                logger.info(
                    "Fused results from %d query variants: %d results",
                    len(all_results),
                    len(vector_results),
                )
            else:
                vector_results = all_results[0] if all_results else []

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

            # Stage 2: Reranking (if enabled)
            if self.reranking_enabled and self.reranking_service and vector_results:
                try:
                    vector_results = await self.reranking_service.rerank(
                        query=user_input,
                        chunks=vector_results,
                        top_n=self.reranker_top_n,
                    )
                    logger.info(
                        "[_execute_retrieval] After reranking: result_count=%d",
                        len(vector_results),
                    )
                except Exception as e:
                    logger.warning("Reranking failed, using original results: %s", e)

            # Pack context by token budget (feature-flag gated by context_max_tokens > 0)
            if vector_results and settings.context_max_tokens > 0:
                temp_sources = [
                    RAGSource(
                        text=r.get("text", ""),
                        file_id=str(r.get("file_id", "")),
                        score=r.get("_distance", 0.0),
                        metadata=r.get("metadata", {}),
                    )
                    for r in vector_results
                ]
                packed_sources = self._pack_context_by_token_budget(
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
                    "Token packing: %d results → %d results (budget=%d tokens)",
                    len(temp_sources),
                    len(packed_sources),
                    settings.context_max_tokens,
                )
            else:
                if vector_results and settings.context_max_tokens <= 0:
                    logger.info(
                        "Token packing: disabled (context_max_tokens=%d)",
                        settings.context_max_tokens,
                    )

            # Final limit to retrieval_top_k
            vector_results = vector_results[: self.retrieval_top_k]

            # Retrieval evaluation (CRAG-style self-evaluation)
            relevance_hint: Optional[str] = None
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
                        relevance_hint = "Note: The retrieved documents may not be directly relevant to your query."
                    elif eval_result == "AMBIGUOUS":
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "Retrieval evaluation: AMBIGUOUS for query '%s'",
                                user_input,
                            )
                except Exception as e:
                    logger.warning("Retrieval evaluation failed: %s", e)

            return vector_results, relevance_hint, eval_result
        except Exception as exc:
            logger.exception(
                "[_execute_retrieval] UNHANDLED EXCEPTION in retrieval pipeline: %s, query=%.100s, vault_id=%s",
                type(exc).__name__,
                user_input,
                vault_id,
            )
            raise

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
    ) -> Dict[str, Any]:
        """Build the final done message with sources.

        Args:
            relevant_chunks: Filtered relevant chunks
            memories: Retrieved memories

        Returns:
            Done message dictionary
        """
        retrieval_debug: Dict[str, Any] = {
            "max_distance_threshold": self.max_distance_threshold,
            "vector_metric": self.vector_metric,
            "retrieval_top_k": self.retrieval_top_k,
        }

        score_type = "rerank" if self.reranking_enabled else "distance"

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

        return {
            "type": "done",
            "sources": sources,
            "memories_used": [mem.content for mem in memories],
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
    ) -> List[RAGSource]:
        """
        Pack context chunks by token budget, respecting max token limit.

        Args:
            chunks: List of RAGSource chunks to pack
            max_tokens: Maximum tokens allowed (default 6000)

        Returns:
            List of RAGSource chunks that fit within the token budget
        """
        packed, token_count = [], 0
        for chunk in chunks:
            # ~3.5 chars/token for English; errs on the side of overestimation
            # to prevent context overflow (safer than the previous len//4 undercount)
            chunk_tokens = max(1, int(len(chunk.text) / 3.5))
            if token_count + chunk_tokens > max_tokens and packed:
                break
            packed.append(chunk)
            token_count += chunk_tokens
        return packed

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
