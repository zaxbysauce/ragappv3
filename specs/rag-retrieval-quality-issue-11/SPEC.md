# RAG Retrieval Quality — Issue 11: Token Packing, Primary Evidence Split, Anchor Best Chunk

## Problem

Three interrelated retrieval-quality issues in the RAG pipeline:

1. **Token packing (greedy early-break):** The legacy greedy strategy stops packing as soon as a chunk doesn't fit, leaving budget headroom unfilled when a smaller subsequent chunk could have fit.
2. **Primary evidence split formula:** `min(max(n // 2, 3), total_chunks)` returned 3 for n=7 (default `reranker_top_n`), giving only 3 chunks primary treatment instead of the expected 5.
3. **Lost-in-the-middle:** The highest-scoring chunk is the most relevant, but LLMs tend to under-utilize context in the middle of long prompts. No mitigation existed.

## Goals

- Replace greedy packing with `reserved_best_fit`: top-3 chunks always included (inviolable), remaining chunks packed with best-fit (no early break).
- Fix primary evidence count formula so n=7 → 5 (not 3).
- Add `anchor_best_chunk`: repeat the top-ranked chunk at the end of context as a lost-in-the-middle mitigation, skipped when the top chunk exceeds 50% of `context_max_tokens`.

## Non-goals

- Text truncation of reserved chunks (tracked as follow-up).
- Changes to retrieval scoring or reranking.
- UI changes.

## Technical design

### New settings (`app/config.py`)
| Setting | Type | Default | Purpose |
|---|---|---|---|
| `token_pack_strategy` | str | `reserved_best_fit` | `reserved_best_fit` or `greedy` (legacy) |
| `primary_evidence_count` | int | 0 | Override primary chunk count; 0 = use formula |
| `anchor_best_chunk` | bool | True | Enable anchor mitigation |

### `_pack_context_by_token_budget` (`rag_engine.py`)
- Returns `Tuple[List[RAGSource], Dict[str, int]]` instead of `List[RAGSource]`.
- Stats: `token_pack_included`, `token_pack_skipped`, `token_pack_truncated`.
- `reserved_best_fit`: reserve top-3, then iterate remaining with best-fit (no break on overflow).
- `greedy`: legacy behavior preserved exactly.
- Stats surfaced in `retrieval_debug` via `_build_done_message`.

### `calculate_primary_count` (`prompt_builder.py`)
- New formula: `min(max(n - 2, 3), min(n, 5))`.
- Results: n=0→0, 1→1, 2→2, 3→3, 4→3, 5→3, 6→4, 7→5, 8+→5.
- `PRIMARY_EVIDENCE_COUNT > 0` overrides formula (capped by total chunks).

### Anchor best chunk (`prompt_builder.py`)
- After primary/supporting sections, repeat top chunk with `[BEST MATCH — repeated for emphasis]` header.
- Skipped if `top_chunk_tokens > context_max_tokens * 0.5`.

## Acceptance criteria

- [ ] `_pack_context_by_token_budget` returns `(chunks, stats)` tuple with all three stat keys.
- [ ] `reserved_best_fit` never skips top-3 chunks regardless of budget.
- [ ] `reserved_best_fit` continues evaluating rank-4+ after overflow (no early break).
- [ ] `greedy` strategy preserved exactly (early break on first overflow after first chunk).
- [ ] `token_pack_included` equals `len(packed)`.
- [ ] `calculate_primary_count(7)` returns 5.
- [ ] `anchor_best_chunk=True` causes top chunk text to appear twice in the user message.
- [ ] Anchor skipped when top chunk > 50% of `context_max_tokens`.
- [ ] All existing tests pass (52/52).

## Test files

- `backend/tests/test_token_packing.py` — `TestGreedyStrategy` + `TestReservedBestFitStrategy`
- `backend/tests/test_calculate_primary_count.py` — formula + override coverage
- `backend/tests/test_prompt_builder_citations.py` — `TestAnchorBestChunk` (5 tests)
- `backend/tests/test_exact_match_promote.py` — updated for 11-element return tuple

## Implementation status

**Complete.** All changes committed to `claude/fix-swarm-ingest-issues-yUtrl`. 52/52 tests pass.
