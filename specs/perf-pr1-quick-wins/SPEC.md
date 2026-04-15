# PR1 — Backend Performance Quick Wins

## Problem statement

Five validated performance regressions identified in the KnowledgeVault codebase
(issue #20, PERF-1/PERF-2/PERF-4/PERF-10/PERF-11) impose unnecessary latency on
the query path and polling UI. All five are independent, surgical fixes with no
architectural dependencies between them.

## Scope

**In scope:** PERF-1, PERF-2, PERF-4, PERF-11 (four of the five findings).

**Out of scope:** PERF-10 (`useSendMessage.ts` parallel saves) — deferred because
SQLite uses second-level timestamp precision for `created_at` in `chat_messages`.
Parallelising the two `addChatMessage` calls would produce identical timestamps
and break `ORDER BY created_at ASC` retrieval ordering. Requires a schema change
(microsecond precision or explicit sequence column) before it is safe.

## Changes

### PERF-1 — Parallelise embedding calls (`rag_engine.py`)

**Problem:** `RAGEngine.query()` embeds each query variant (original, step-back,
HyDE) in a sequential `for` loop. Embedding calls are I/O-bound and independent;
serialising them adds the full round-trip latency of each variant to the critical
path.

**Fix:** Replace the loop with `asyncio.gather(*tasks, return_exceptions=True)`.
Error handling is preserved post-gather: `original` variant failures still raise
`RAGEngineError` immediately; non-original failures still drop the variant and log
a warning. The fix also handles non-`EmbeddingError` exceptions (e.g.
`CircuitBreakerError`) that the original loop would have propagated unhandled.

**Files changed:** `backend/app/services/rag_engine.py`

### PERF-2 — O(1) LRU cache in QueryTransformer (`query_transformer.py`)

**Problem:** `QueryTransformer` maintains two manual LRU caches using a `dict` +
`list` pair. Every cache hit and every cache update calls `list.remove(key)`,
which is O(n) (scans the full list). With a max capacity of 1024 entries, each
access costs up to ~512 comparisons.

**Fix:** Replace both `dict+list` pairs with `collections.OrderedDict`.
`OrderedDict.move_to_end(key)` and `popitem(last=False)` are both O(1). The
`_lru_keys` and `_lru_hyde_keys` list attributes are removed entirely.

**Files changed:** `backend/app/services/query_transformer.py`

### PERF-4 — Class-level semaphore in VectorStore (`vector_store.py`)

**Problem:** `VectorStore.search()` creates `asyncio.Semaphore(_MULTI_SCALE_CONCURRENCY)`
as a local variable on every call. Because the semaphore is local, it provides no
cross-call concurrency control — each request gets its own semaphore. Additionally,
the single-scale search path (the majority code path) has no semaphore at all.

**Fix:** Promote the semaphore to a class-level lazily-initialised attribute
(`_search_semaphore`, created on first use via `_get_search_semaphore()`). The
class-level instance is shared across all concurrent callers, limiting total
concurrent LanceDB searches to `_MULTI_SCALE_CONCURRENCY = 4`. The single-scale
path is now wrapped with `async with self._get_search_semaphore():` (with the
`table is None` early-return guard kept outside the semaphore). The multi-scale
nested function captures the semaphore via a local `_semaphore` variable to avoid
a direct `self` reference inside the closure.

Lazy init is used (not `__init__`) to avoid asyncio event-loop binding issues on
Python < 3.10.

**Files changed:** `backend/app/services/vector_store.py`

### PERF-11 — Adaptive polling backoff in DocumentsPage (`DocumentsPage.tsx`)

**Problem:** `DocumentsPage` polls for document processing status every fixed 5 s
via `setInterval`. This creates unnecessary backend load when processing is slow
or has completed, and is unresponsive when processing is fast.

**Fix:** Replace `setInterval` with a `setTimeout`-based adaptive backoff loop
using a `useRef` (so the interval state persists across renders without causing
re-renders). Behaviour:
- Starts at 2 s when documents enter processing/pending state
- Backs off 1.5× per poll cycle, capped at 30 s
- Resets to 2 s when processing stops (so the next batch starts fast)
- React `useEffect` cleanup (`clearTimeout`) prevents double-firing when
  `documents` state updates between polls

**Files changed:** `frontend/src/pages/DocumentsPage.tsx`

## Acceptance criteria

### PERF-1
- [ ] `RAGEngine.query()` no longer contains a sequential `for` loop with `await`
      inside for embedding variant queries
- [ ] Uses `asyncio.gather(*tasks, return_exceptions=True)` for concurrent embedding
- [ ] An `EmbeddingError` on the `original` variant raises `RAGEngineError` (same
      as before)
- [ ] An `EmbeddingError` on a non-original variant logs a warning and appends to
      `variants_dropped` without raising (same as before)
- [ ] Non-`EmbeddingError` exceptions from embedding calls are also handled (new
      robustness improvement)

### PERF-2
- [ ] `QueryTransformer.__init__` no longer declares `_lru_keys` or `_lru_hyde_keys`
- [ ] Both LRU caches are `OrderedDict` instances
- [ ] Cache hit calls `move_to_end(key)` instead of `list.remove(key)`
- [ ] Cache eviction calls `popitem(last=False)` instead of `list.pop(0)` + `del`
- [ ] LRU capacity limit (1024) is still enforced for both caches

### PERF-4
- [ ] `VectorStore.__init__` declares `self._search_semaphore: Optional[asyncio.Semaphore] = None`
- [ ] `_get_search_semaphore()` creates the semaphore lazily on first call
- [ ] Multi-scale path uses `self._get_search_semaphore()` (not a new local `asyncio.Semaphore(...)`)
- [ ] Single-scale path wraps the search block in `async with self._get_search_semaphore():`
- [ ] `if self.table is None: return []` guard remains outside the semaphore

### PERF-11
- [ ] `pollIntervalMsRef = useRef(2_000)` is declared (not `useState`)
- [ ] Polling effect uses `setTimeout` (not `setInterval`)
- [ ] Interval backs off by 1.5× each cycle, capped at 30 s
- [ ] Interval resets to 2 s when `hasProcessingDocs` becomes false
- [ ] `useEffect` cleanup calls `clearTimeout` (not `clearInterval`)
- [ ] `pollIntervalMsRef` is NOT in the `useEffect` dependency array

## Non-goals

- No schema changes to `chat_messages` (PERF-10 deferred)
- No changes to `useSendMessage.ts`
- No changes to the RAG pipeline architecture (PR7 scope)
- No new user-visible features

## Test cases

| # | Scenario | Expected |
|---|---|---|
| T1 | RAG query with 3 variants — all embed successfully | All 3 embeddings complete; query proceeds |
| T2 | RAG query — `original` variant embedding raises `EmbeddingError` | `RAGEngineError` raised; stream/non-stream both handled |
| T3 | RAG query — step-back variant embedding raises `EmbeddingError` | Variant dropped, `variants_dropped` appended, query continues with remaining variants |
| T4 | `QueryTransformer` — cache hit on existing key | Key moved to end (MRU); existing `_lru_keys` attribute no longer exists |
| T5 | `QueryTransformer` — cache set beyond 1024 entries | Oldest key evicted via `popitem(last=False)` |
| T6 | `VectorStore.search()` single-scale — 5 concurrent callers | At most 4 execute concurrently (semaphore shared) |
| T7 | `VectorStore.search()` — `table is None` | Returns `[]` without acquiring semaphore |
| T8 | `DocumentsPage` — documents enter processing state | Polling starts at 2 s |
| T9 | `DocumentsPage` — no status change between polls | Interval backs off to 3 s, then 4.5 s, etc. |
| T10 | `DocumentsPage` — processing completes | Interval resets to 2 s for next batch |

## Decisions log

| Decision | Rationale |
|---|---|
| PERF-10 deferred | SQLite `CURRENT_TIMESTAMP` has second-level precision. `Promise.all` on both saves within the same second produces identical timestamps, breaking `ORDER BY created_at ASC`. Safe parallelisation requires a schema migration. |
| Lazy semaphore init (not `__init__`) | `asyncio.Semaphore()` in `__init__` can bind to the wrong event loop on Python 3.8/3.9. Lazy init in `_get_search_semaphore()` creates the semaphore in the active event loop context on first use. |
| `_semaphore` local var in multi-scale closure | The nested `_sem_search_single_scale` function captures `_semaphore` (a local reference to `self._get_search_semaphore()`) rather than calling `self._get_search_semaphore()` inside the closure. Both are equivalent, but the local var makes the capture explicit and avoids repeated `self` lookups inside a hot async closure. |
| `elif isinstance(result, Exception)` in PERF-1 | The original loop only caught `EmbeddingError`. The new post-gather pass also handles generic exceptions (e.g. `CircuitBreakerError` which can escape `embed_single`). This is strictly more robust than the original. |
