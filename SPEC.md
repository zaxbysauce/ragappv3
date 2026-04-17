# RAGv3 Deployment Fixes: Embedding & Spreadsheet Chunking

## Problem Statement

The RAGv3 remote deployment (minimax m2.7) experienced three critical failures during document ingestion:

1. **Embedding batch size mismatch**: The TEI embedding service accepts max 32 sequences per request, but the application was configured to send 512, causing `422 Validation: batch size 512 > maximum allowed batch size 32` errors.

2. **Spreadsheet chunks exceeding embedding limit**: Wide spreadsheets (100+ columns × 50 rows) produced chunks of 20,000+ characters, exceeding the 8192-char embedding model input limit. Documents like `T6_DCW_data_dictionary.xlsx` failed with `Text at index 0 exceeds maximum length (8192 characters)`.

3. **No pre-embedding visibility**: No early warning before chunks reached the embedding service, making it difficult to diagnose chunking strategy issues.

Additionally, a configuration validator mismatch created a deployment risk: the settings UI allowed batch sizes up to 2048, but the config validator capped it at 128, causing silent config loss on restart.

## Goals

1. Prevent embedding batch size errors by aligning default and validated range with TEI's actual limit
2. Prevent data loss from wide spreadsheets by splitting them into column groups instead of truncating
3. Provide pre-embedding visibility for debugging
4. Fix the settings UI validator to prevent silent config loss

## Scope

### In Scope
- Embedding batch size configuration (env var, validator, default)
- Spreadsheet column-group chunking (adaptive algorithm, no data loss)
- Pre-embedding validation and logging
- Settings UI validator alignment
- Tests covering wide spreadsheets and edge cases
- Critical bug fix: single-column overflow validation

### Out of Scope
- LLM service connectivity (separate infrastructure issue)
- Batch API response pooling or optimization
- Historical config migration for existing 512 values

## Acceptance Criteria

### Batch Size Fix
- [ ] `EMBEDDING_BATCH_SIZE` environment variable defaults to 32 in docker-compose.yml
- [ ] Config validator caps batch size at 128 for safety headroom
- [ ] Settings UI validator matches config validator (max 128)
- [ ] Default config value is 32 (aligns with env var default)

### Spreadsheet Chunking Fix (Data-Preserving)
- [ ] Wide spreadsheets (100+ columns) no longer truncate data
- [ ] Chunks are split by column groups when a single row exceeds 8192 chars
- [ ] Each chunk is self-contained: includes sheet name + column headers for its group + values
- [ ] All chunks respect MAX_CHUNK_CHARS limit (8192)
- [ ] No data loss except single cell values > 8192 (unavoidable; only that cell)
- [ ] Column-group chunks marked with `col_group` metadata for identification

### Pre-Embedding Validation
- [ ] `_validate_chunk_sizes()` method logs warnings for oversized chunks before embedding
- [ ] Runs immediately before `embed_batch()` call
- [ ] Provides early visibility for debugging

### Test Coverage
- [ ] Wide spreadsheet test (100 cols × 1000-char values): verifies column splitting
- [ ] Non-uniform column test: catches single-column overflow edge case
- [ ] Mixed row sizes test: validates adaptive behavior across rows
- [ ] All tests verify chunks ≤ 8192 chars
- [ ] All tests verify no data loss (all columns present)

### Configuration Consistency
- [ ] Settings UI validator max matches config.py validator max (128)
- [ ] No silent config loss when users set values > 128

## Technical Design

### Batch Size
- Docker-compose.yml: `EMBEDDING_BATCH_SIZE=${EMBEDDING_BATCH_SIZE:-32}`
- Config default: `embedding_batch_size: int = 32`
- Config validator: `_validate_int_range(v, 1, 128, ...)`
- Settings UI validator: cap at 128 (matching config)

### Spreadsheet Chunking (Column-Group Algorithm)
- **Method**: `SpreadsheetParser._split_row_by_columns(col_val_pairs, sheet_name, row_idx, total_rows, total_col_count)`
  - Greedy column accumulation into groups
  - When adding a column would exceed 8192 chars:
    - Flush current group as a chunk
    - Start new group with that column
    - If the single column exceeds 8192, truncate only that cell
  - Each chunk: `Sheet: X\nColumns: col1 | col2\n\ncol1: val1 | col2: val2`

- **Integration**: Single-row overflow path (when `rows_per_chunk == 1`) calls `_split_row_by_columns()` instead of truncating
- **Metadata**: Chunks marked with `col_group: int` (0-indexed group number within the row)

### Validation Before Embedding
- `DocumentProcessor._validate_chunk_sizes(texts, source_filename)`
- Runs before `embed_batch()` call
- Logs warning for each chunk > MAX_TEXT_LENGTH (8192)
- Does not prevent embedding (observability only; embedding service has its own truncation safeguard)

## Test Cases

### test_single_row_with_long_cell_values_no_data_loss
- **Input**: 10 columns × 1000-char values (total ~10,270 chars)
- **Expected**: Multiple column-group chunks
- **Verify**: All chunks ≤ 8192, all columns present, col_group metadata exists

### test_non_uniform_column_sizes_triggers_validation
- **Input**: 5 moderate columns (~500 chars each) + 1 huge column (~10,000 chars)
- **Expected**: Multiple chunks with validation catching the huge column
- **Verify**: All chunks ≤ 8192, huge column truncated, moderate columns intact

### test_mixed_row_sizes_with_column_splitting
- **Input**: 50 columns with varying row densities (some normal, some 500-char values)
- **Expected**: Multiple chunks from adaptive row reduction + column splitting
- **Verify**: All chunks ≤ 8192, no data loss

## Known Limitations

1. **Single cell > 8192 chars**: Unavoidable data loss for cells larger than the embedding model's max input. Only that cell's value is truncated; all other columns are preserved.

2. **Retrieval for split rows**: A user query might return multiple column-group chunks for the same row. The LLM sees column names and values but must reason across chunks for the full row context. This is acceptable for RAG pipelines.

3. **Existing configs with batch size > 128**: Will silently reset to 32 (env default) on next restart. Logged as warning. No migration script provided — users can manually re-set if needed.

## Implementation Notes

- Column-group chunking replaces the truncation hack from the initial fix
- All column data is preserved (no truncation of column metadata or values)
- Critical bug fix: Added validation for single-column overflow that prevents chunks from exceeding 8192 chars
- Settings validator change is a breaking change (2048 → 128 cap) but addresses a deployment risk

## Verification Checklist

- [ ] All batch size settings properly configured
- [ ] Spreadsheet chunking algorithm prevents data loss
- [ ] Column-group tests catch edge cases
- [ ] Pre-embedding validation logs visibility
- [ ] Settings validators aligned
- [ ] Critical overflow bug fixed
- [ ] All quality gates pass (tests, typecheck, lint)
- [ ] Documentation updated
- [ ] PR description comprehensive
- [ ] Reviewer feedback addressed
