# Resolve Swarm Issues #2, #12, #13, #14

## Problem Statement

Four open GitHub issues representing significant tech debt and missing features in the KnowledgeVault RAG pipeline:

- **#14**: Upload API silently defaulted `vault_id=1` when no vault was specified, causing documents to land in the orphan vault without operator awareness.
- **#12**: The retrieval pipeline retrieved small chunks for precision but only sent those small chunks to the LLM, discarding surrounding context. Additionally, the UID-strip deduplication logic collapsed multiple strong chunks from the same document into a single result.
- **#13**: Multiple ingestion integrity gaps: chunks from files still being indexed were visible to queries (partial-document answers); re-uploading a file created a zero-chunk window during the delete-then-insert sequence; the ANN vector index was never rebuilt after large deletes, degrading search quality silently.
- **#2**: After the Harrier embedding migration (BGE-M3 768-dim → Harrier 1024-dim), no tooling or documentation existed to guide operators through re-indexing their document corpus. The health endpoint gave no warning when stale embeddings were detected.

## Goals

Ship all four issues fully wired and production-ready with no deferred work.

## Non-Goals

- Frontend changes
- Migration auto-run on startup (operators trigger manually)
- Streaming parent window content

---

## Acceptance Criteria

### Issue #14 — vault_id required on upload

- [x] `POST /api/documents` and `POST /api/documents/upload` return HTTP 422 when `vault_id` query parameter is absent
- [x] No silent assignment to vault 1
- [x] Source verification: `vault_id: int = Query(...)` (Ellipsis, no default) on both endpoints

### Issue #12 — Parent-document retrieval (small-to-big)

- [x] LanceDB schema includes `parent_doc_id`, `parent_window_start`, `parent_window_end`, `chunk_position` columns (nullable, backwards-compatible)
- [x] `compute_parent_windows()` in `chunking.py` locates each chunk's text in the source document and computes a ±3000-char window (default 6000 chars total), clamped to document bounds
- [x] `compute_parent_windows` prefers `raw_text` (pre-enrichment text) over enriched `text` when locating matches in source
- [x] Parent window text is stored in chunk metadata at ingest time (no file I/O at retrieval time)
- [x] When `PARENT_RETRIEVAL_ENABLED=true`, the RAG engine reads `parent_window_text` from metadata and attaches it to `RAGSource` objects
- [x] `prompt_builder.format_chunk` renders `[[MATCH: <chunk_text>]]` anchor within the parent window when `parent_retrieval_enabled=True`
- [x] When match text is not found in parent window, falls back to appending `[[MATCH: ...]]` annotation after parent text
- [x] Group-aware dedup replaces UID-strip dedup: max `PER_DOC_CHUNK_CAP` (default 2) chunks per document, max `UNIQUE_DOCS_IN_TOP_K` (default 5) distinct documents in result set
- [x] `app/migrations/add_parent_window.py` CLI migration is idempotent, supports `--dry-run`, backfills existing rows with `parent_doc_id=file_id` and `chunk_position=chunk_index`
- [x] All new behaviour behind feature flags with safe defaults (`PARENT_RETRIEVAL_ENABLED=false`, `NEW_DEDUP_POLICY=true`)

### Issue #13 — Ingestion integrity

- [x] Chunks from files with `status != 'indexed'` are excluded from `filter_relevant` results (atomic visibility via `indexed_file_ids` set)
- [x] When `REUPLOAD_SAFE_ORDER=true` (default): new chunks are inserted before old chunks are deleted, eliminating the zero-chunk window on re-upload
- [x] New-generation chunks use hash-prefixed IDs (`{file_id}_{hash8}_{scale}_{idx}`); `delete_old_generation_by_file` removes only old-generation rows
- [x] `table.optimize()` is called after every `add_chunks` batch (non-fatal on failure)
- [x] `_maybe_rebuild_or_drop_vector_index(deleted_count)` is called after every `delete_by_file` and `delete_by_vault`: drops IVF_PQ index when rows fall below 256; rebuilds when churn ≥ `INDEX_REBUILD_DELTA` (default 0.20)
- [x] `app/migrations/audit_vault_defaults.py` CLI audit identifies vault-1 auto-assigned uploads (read-only, idempotent, `--output-csv` support)

### Issue #2 — Embedding dimension migration tooling

- [x] `README.md` includes an "Upgrading" section with step-by-step re-embedding instructions
- [x] `docs/release.md` documents the Harrier migration as a breaking change requiring re-embedding
- [x] `scripts/migrate_embeddings.py` detects dimension mismatch, wipes LanceDB, resets file statuses to `pending`, supports `--dry-run` and `--force`; is a no-op on fresh deployments
- [x] `/api/health?deep=true` returns `"stale_embeddings": true` in `vector_store` when stored embedding dimension ≠ `EMBEDDING_DIM`; logs a `WARNING`

---

## Technical Design

### Parent window storage strategy
Parent window text is computed at ingest time and stored in `chunk.metadata["parent_window_text"]`. This avoids re-opening PDF/DOCX files at query time. The `compute_parent_windows()` function runs a single linear scan over all chunks for O(n) performance.

### Safe re-upload ID scheme
New chunks get IDs of the form `{file_id}_{hash8}_{scale}_{index}`. The `delete_old_generation_by_file(file_id, hash8)` method deletes rows matching `file_id = X AND NOT (id LIKE '{file_id}_{hash8}_%')`. This allows new and old generation chunks to coexist momentarily, eliminating the zero-chunk gap.

### Atomic visibility
`rag_engine.py` fetches `indexed_file_ids` from SQLite via `asyncio.to_thread` before each query. The set is passed to `filter_relevant`, which skips any chunk whose `file_id` is not in the set. On failure, `indexed_file_ids=None` disables filtering gracefully.

### Group-aware dedup
Two-pass cap: `count_per_doc[file_id] >= PER_DOC_CHUNK_CAP` skips over-represented docs; `len(selected_docs) >= UNIQUE_DOCS_IN_TOP_K and file_id not in selected_docs` caps breadth. Iteration order preserved (descending relevance).

### ANN index lifecycle
`_last_index_build_row_count` tracked at every IVF_PQ build. On delete: if `current_rows < 256` → drop index (brute-force fallback); if `deleted_count / last_build_count >= INDEX_REBUILD_DELTA` → rebuild. Zero-row `last_build_count` skips the churn check.

### Health check stale embedding detection
`VectorStore._get_expected_embedding_dim()` reads the embedding field's `list_size` from the LanceDB schema. Compared against `settings.embedding_dim` in the deep health check.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PARENT_RETRIEVAL_ENABLED` | `false` | Enable small-to-big context expansion |
| `PARENT_WINDOW_CHARS` | `6000` | Total window size in characters (±3000 around match) |
| `NEW_DEDUP_POLICY` | `true` | Use group-aware dedup |
| `PER_DOC_CHUNK_CAP` | `2` | Max chunks per document |
| `UNIQUE_DOCS_IN_TOP_K` | `5` | Max distinct documents in result set |
| `INDEX_REBUILD_DELTA` | `0.2` | Delete churn fraction to trigger ANN rebuild |
| `REUPLOAD_SAFE_ORDER` | `true` | Insert new chunks before deleting old on re-upload |

---

## Test Cases

### Issue #14
- Upload without `vault_id` → HTTP 422
- Route source confirms `Query(...)` with no default (verified via source inspection)

### Issue #12 — `compute_parent_windows`
- Basic window computation: match text found inside window bounds
- Window clamped to document bounds (no overflow)
- `raw_text` used preferentially for locating match in source
- Chunk not found in source → offsets remain `None`
- 10,000-char source with 3 chunks → all get valid windows
- Sequential `chunk_position` assignment
- Empty chunk list → empty result
- Empty source text → offsets `None`

### Issue #12 — `_group_aware_dedup`
- Two strong chunks from same doc both survive with `cap=2`
- Third chunk from same doc dropped
- Max `unique_docs_in_top_k` distinct file_ids enforced
- Core scenario: doc with 6 chunks contributes exactly 2
- Ranking order preserved in output
- Empty input → empty output

### Issue #12 — Prompt builder
- `[[MATCH: ...]]` inserted when `parent_retrieval_enabled=True`
- No marker when `parent_retrieval_enabled=False`
- Fallback annotation when match text not found in parent window

### Issue #12 — Migration
- Dry run returns 0 when all rows already have `parent_doc_id`
- Idempotent: two runs both return 0 when up-to-date
- Returns 0 when no `chunks` table exists

### Issue #13 — ANN index lifecycle
- `deleted_count=0` → no table ops called
- `rows < 256` with IVF_PQ → index dropped, `_last_index_build_row_count` reset
- No drop when no IVF_PQ index exists
- Churn ≥ delta → index rebuilt, `_last_index_build_row_count` updated
- Churn < delta → no rebuild
- `_last_index_build_row_count=0` → churn check skipped

### Issue #13 — optimize()
- `optimize()` awaited once per `add_chunks` call
- `optimize()` failure is non-fatal (no exception propagated)

### Issue #13 — Visibility filter
- Chunks from non-indexed files excluded when `indexed_file_ids` provided
- Chunks from indexed files returned
- `indexed_file_ids=None` disables filter
- Empty `indexed_file_ids` set hides all chunks

### Issue #13 — Safe re-upload
- `delete_old_generation_by_file` returns correct deleted count
- New-generation chunks preserved (0 deleted when all match prefix)
- During transition: both generations coexist (no zero-chunk window)
- Delete filter targets correct file_id and hash prefix

### Issue #13 — Audit migration
- Flags `vault_id=1 AND source='upload' AND status='indexed'` docs
- Ignores other vaults
- Ignores non-indexed status
- Ignores non-upload source
- Empty files table → empty result
- Non-existent db → empty result (no crash)
- Missing `source` column → fallback query (flags all vault-1 indexed)
- Idempotent: two runs return same count

---

## Files Changed

### Modified
- `backend/app/api/routes/documents.py` — vault_id required
- `backend/app/api/routes/health.py` — stale embedding warning
- `backend/app/config.py` — 7 new config fields + validators
- `backend/app/services/chunking.py` — `compute_parent_windows()`, `ProcessedChunk` fields
- `backend/app/services/document_processor.py` — parent window ingest, safe re-upload
- `backend/app/services/document_retrieval.py` — `_group_aware_dedup()`, `RAGSource.parent_window_text`, `indexed_file_ids` filter
- `backend/app/services/prompt_builder.py` — `[[MATCH:]]` rendering
- `backend/app/services/rag_engine.py` — `indexed_file_ids` lookup, parent window expansion
- `backend/app/services/vector_store.py` — schema, ANN lifecycle, optimize, safe re-upload delete, migration
- `docs/release.md` — v0.2.0 release notes
- `README.md` — Upgrading section

### Created
- `backend/app/migrations/__init__.py`
- `backend/app/migrations/add_parent_window.py`
- `backend/app/migrations/audit_vault_defaults.py`
- `backend/tests/test_parent_retrieval.py` (22 tests)
- `backend/tests/test_ingestion_integrity.py` (27 tests)
- `scripts/migrate_embeddings.py`
