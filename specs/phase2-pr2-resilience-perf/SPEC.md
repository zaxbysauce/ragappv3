# Phase 2 / PR 2 — Resilience, Security & Performance Leftover

## Problem Statement

Following the phase-1 performance quick-wins PR (PERF-1, PERF-2, PERF-4, PERF-11), six
validated findings from issue #20 remained unimplemented:

- **PERF-10**: User and assistant chat messages are saved to the API sequentially after
  stream completion, adding unnecessary latency to every chat turn.
- **RES-1**: Vector store `connect()` and `init_table()` failures are swallowed by
  `_safe_await`, allowing the app to start with a broken or missing vector store. Any
  subsequent request will fail at runtime rather than at startup.
- **RES-3**: No lightweight readiness probe exists. The only health endpoint (`/api/health`)
  always returns `{"status":"ok"}` regardless of actual service state, making it useless
  for Kubernetes liveness/readiness probes or load-balancer health checks.
- **RES-5**: The email ingestion polling task (`asyncio.create_task`) is fire-and-forget.
  Unhandled exceptions that escape the known exception types (`OSError`, `RuntimeError`,
  `ConnectionError`) silently crash the task, leaving the service appearing healthy while
  email ingestion has stopped.
- **RES-7**: `reject_insecure_defaults()` only validates `ADMIN_SECRET_TOKEN` and
  `JWT_SECRET_KEY` when `USERS_ENABLED=True`. In single-admin mode (`USERS_ENABLED=False`)
  the admin token is the **sole** authentication mechanism — starting without one means the
  app has zero authentication.
- **RES-15**: The axios client instance has no timeout. A hung backend connection will block
  the UI indefinitely.

## Goals

1. Parallelise post-stream message saves for lower chat latency (PERF-10).
2. Abort startup when the vector store cannot connect or initialise its table (RES-1).
3. Add `/api/healthz` — a fast, unauthenticated readiness probe that returns 503 when
   critical services are not ready (RES-3).
4. Log and surface unhandled email polling task failures via a task done-callback; prevent
   unknown exceptions from silently killing the loop (RES-5).
5. Raise `ValueError` at startup when the app is in single-admin mode with no admin token
   set (RES-7).
6. Add `timeout: 30000` to the axios instance so UI requests cannot hang indefinitely;
   exempt file uploads from this timeout (RES-15).

## Non-Goals

- No changes to PR 3–7 scope (accessibility, UI perf, API layer cleanup, UX polish,
  architecture refactor).
- No changes to email service IMAP logic or polling interval configuration.
- No new user-facing UI for healthz (probe-only endpoint).

## Acceptance Criteria

### PERF-10
- [x] `onComplete` in `useSendMessage.ts` saves user message and assistant message
  concurrently via `Promise.all`, not sequentially.
- [x] If `assistantMsg` is not found in the store, only the user message is saved (same
  behaviour as before).
- [x] `refreshHistory()` is still awaited after both saves complete.

### RES-1
- [x] `vector_store.connect()` uses `asyncio.wait_for` directly (no `_safe_await`);
  `TimeoutError` or any exception propagates and aborts startup.
- [x] `vector_store.init_table()` likewise uses `asyncio.wait_for` directly.
- [x] Additive migrations (`migrate_add_vault_id`, etc.) continue to use `_safe_await`
  (non-critical, backward-compatible operations).

### RES-3
- [x] `GET /api/healthz` is registered and reachable (registered under the existing health
  router which is included at `/api` prefix in `main.py`).
- [x] Returns `{"status":"ok"}` (HTTP 200) when `db_pool`, `vector_store`, and
  `embedding_service` are all initialised.
- [x] Returns `{"status":"degraded","issues":[...]}` (HTTP 503) listing which services are
  missing.
- [x] No authentication required on this endpoint.
- [x] Does not perform expensive model/embedding probes (fast, suitable for frequent polling).

### RES-5
- [x] `start_polling()` attaches a `done_callback` (`_on_polling_task_done`) to the asyncio
  task.
- [x] The callback logs at `ERROR` level when the task exits with an unhandled exception and
  sets `_running = False`.
- [x] The callback handles the cancelled-task case cleanly (logs at `INFO`, returns without
  calling `task.exception()`).
- [x] `_polling_loop` catches `Exception` broadly after the specific exception types, logs
  the unexpected error, and `break`s (stopping the service rather than silently re-looping).

### RES-7
- [x] `reject_insecure_defaults()` raises `ValueError` when `users_enabled=False` and
  `admin_secret_token` is empty.
- [x] Existing behaviour for `users_enabled=True` paths is unchanged.
- [x] Test `test_users_disabled_with_empty_admin_token_succeeds` is updated to
  `test_users_disabled_with_empty_admin_token_raises` and asserts `ValueError`.
- [x] The error message includes a token generation command.

### RES-15
- [x] `axios.create(...)` includes `timeout: 30000`.
- [x] `uploadDocument` overrides with `timeout: 0` so large file uploads are not killed by
  the global timeout.

## Technical Design

### PERF-10 — `frontend/src/hooks/useSendMessage.ts`

Replace the two sequential `await addChatMessage(...)` calls in `onComplete` with a
`Promise<unknown>[]` array built conditionally, then `await Promise.all(saves)`.

Message ordering is safe: the backend orders messages by `created_at` (database-assigned
timestamp) and auto-increment `id`, not by client-generated IDs. Concurrent inserts at
near-identical times are ordered by SQLite's autoincrement, preserving user → assistant
ordering.

### RES-1 — `backend/app/lifespan.py`

Replace:
```python
await _safe_await(app.state.vector_store.connect(), "Vector store connect", timeout=15)
await _safe_await(app.state.vector_store.init_table(...), "Vector store init_table", timeout=10)
```
With:
```python
await asyncio.wait_for(app.state.vector_store.connect(), timeout=15)
await asyncio.wait_for(app.state.vector_store.init_table(...), timeout=10)
```
No outer `try/except` wraps these calls in the lifespan startup path.

### RES-3 — `backend/app/api/routes/health.py`

Add a new route `GET /healthz` to the existing `router`. Uses `request.app.state` to check
`db_pool`, `vector_store` (and `vector_store.table`), and `embedding_service`. Returns plain
dict (FastAPI auto-serialises) on success; `JSONResponse(status_code=503, ...)` on failure.
`JSONResponse` import added to the module.

### RES-5 — `backend/app/services/email_service.py`

In `start_polling()`:
```python
self._polling_task = asyncio.create_task(self._polling_loop())
self._polling_task.add_done_callback(self._on_polling_task_done)
```

New method `_on_polling_task_done(task: asyncio.Task)`:
- `if task.cancelled(): return`
- `exc = task.exception()` — safe because `cancelled()` was already checked
- If `exc` is not None: log error, set `self._running = False`

In `_polling_loop`, after `except (OSError, RuntimeError, ConnectionError)`:
```python
except Exception as e:
    self._last_error = str(e)
    logger.error("Unexpected error in email polling loop (stopping service): %s", e, exc_info=True)
    break
```

### RES-7 — `backend/app/config.py`

In `reject_insecure_defaults()`, add after the existing checks:
```python
if not self.users_enabled and not self.admin_secret_token:
    raise ValueError("ADMIN_SECRET_TOKEN must be set when USERS_ENABLED=False ...")
```

### RES-15 — `frontend/src/lib/api.ts`

```typescript
const apiClient = axios.create({ baseURL: API_BASE_URL, timeout: 30000, ... });
```

In `uploadDocument`, add `timeout: 0` to the per-request config to override the global
timeout for file uploads (max upload size is 50 MB; large uploads easily exceed 30 s).

## Files Changed

| File | Change |
|---|---|
| `frontend/src/hooks/useSendMessage.ts` | `Promise.all` for concurrent message saves (PERF-10) |
| `frontend/src/lib/api.ts` | Global 30 s timeout; `timeout: 0` override in `uploadDocument` (RES-15) |
| `backend/app/lifespan.py` | `asyncio.wait_for` for vector store connect + init_table (RES-1) |
| `backend/app/api/routes/health.py` | New `/healthz` readiness probe (RES-3) |
| `backend/app/services/email_service.py` | Task done-callback + broad exception handler (RES-5) |
| `backend/app/config.py` | Single-admin mode insecure-defaults check (RES-7) |
| `backend/tests/test_config_validators.py` | Update stale test to expect `ValueError` (RES-7) |

## Test Plan

### Automated

- `backend/tests/test_config_validators.py` — `TestRejectInsecureDefaults` class covers all
  four validator paths including the new single-admin check.
- Frontend: `vitest run` — type coverage for `useSendMessage.ts` and `api.ts`.

### Manual

- Start app with `USERS_ENABLED=false` and no `ADMIN_SECRET_TOKEN` → should refuse to start.
- Start app normally → `GET /api/healthz` returns 200.
- Send a chat message → both user+assistant saves fire concurrently (confirm via request
  timing in browser dev tools).
- Upload a large file → does not time out after 30 s.
