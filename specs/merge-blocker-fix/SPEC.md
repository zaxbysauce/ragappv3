# Merge-Blocker Fix: Preserve file_id in Async Upload Retry Path

## Problem Statement

The BackgroundProcessor._handle_failure() method was creating retry TaskItems without preserving the `file_id` field. This caused async-uploaded files that failed on the first processing attempt to fall through to `process_file()` (legacy path) on retry, re-running duplicate detection against an already-existing files row, instead of routing to `process_existing_file()` which skips duplicate detection.

Additionally, the admin retry endpoint retry_document() was calling enqueue() without passing file_id, causing the same issue for manually-retried documents.

## Root Cause

Two missing field assignments:
1. `background_tasks.py:_handle_failure()` — TaskItem constructor missing `file_id=task.file_id`
2. `documents.py:retry_document()` — enqueue() call missing `file_id=file_id` parameter

## Acceptance Criteria

- [x] _handle_failure() preserves file_id in retry TaskItem
- [x] Retry tasks with file_id call process_existing_file(), not process_file()
- [x] Legacy tasks (file_id=None) remain unaffected
- [x] Admin retry endpoint passes file_id to enqueue()
- [x] Regression tests cover both code paths

## Technical Design

### Changes

**backend/app/services/background_tasks.py**
- Line 448: Add `file_id=task.file_id,` to the retry TaskItem constructor in _handle_failure()

**backend/app/api/routes/documents.py**
- Line 167: Change `enqueue(row["file_path"], vault_id=row["vault_id"])` to `enqueue(row["file_path"], vault_id=row["vault_id"], file_id=file_id)`

**backend/tests/test_document_progress_async.py**
- Add TestHandleFailurePreservesFileId class with three regression tests
- Add TestAdminRetryPassesFileId class with source-inspection test

### Test Plan

1. Unit test: _handle_failure preserves file_id in retry task
2. Unit test: Legacy tasks (file_id=None) are unaffected
3. Unit test: Retry task with file_id routes to process_existing_file()
4. Source inspection: retry_document enqueue call includes file_id=file_id

## What "Done" Looks Like

- Code changes committed and pushed to claude/swarm-contract-verification-WhKcH
- All new regression tests pass
- PR created, reviewed, and merged
- CI/CD green
- No code regressions
