# Codebase QA Report

**Generated:** 2026-04-03
**Scope:** Full repository `/home/user/ragappv3` — backend (Python/FastAPI), frontend (React/TypeScript), infrastructure (Docker, scripts)
**Files reviewed:** ~320 source files across 6 parallel analysis scopes + direct reading
**Claude bootstrap used:** YES
**Claimed-vs-shipped verification:** YES

**VERDICT: REJECTED**
**RISK: CRITICAL**

## Executive Summary

The KnowledgeVault codebase has **1 critical supply-chain issue** (missing auth dependencies in requirements.txt that will crash the app on any auth operation), **multiple high-severity authorization flaws** (any authenticated user can modify server settings, unauthenticated endpoints leak infrastructure info, SSRF via settings), **significant doc-to-code drift** (README claims features not actually supported), and **systemic frontend security issues** (JWT stored in localStorage, missing sanitization). The codebase is functional in its core RAG pipeline but has serious gaps in security hardening, authorization granularity, and documentation accuracy.

## Findings Count

```
Group 1 (Behavior):           0 / 3 / 7 / 1 / 0
Group 2 (Substance/Wiring):   0 / 2 / 3 / 2 / 1
Group 3 (Security):           1 / 6 / 10 / 5 / 1
Group 4 (Dependencies):       1 / 1 / 2 / 0 / 0
Group 5 (Claimed vs Shipped): 0 / 3 / 2 / 0 / 0
Group 6 (Cross-Platform):     0 / 1 / 2 / 0 / 0
Group 7 (AI Smells):          0 / 0 / 5 / 0 / 0
Group 8 (Architecture/Perf):  0 / 0 / 1 / 0 / 0
Group 9 (Tests):              0 / 1 / 6 / 3 / 0
------------------------------------------------
TOTAL:                        2 / 17 / 38 / 11 / 2

AI Pattern Distribution:
  mapping-hallucination: 0
  naming-hallucination: 0
  resource-hallucination: 0
  logic-hallucination: 0
  claim-hallucination: 3
  phantom-dependency: 0
  stale-api: 0
  context-rot: 1
  unwired-functionality: 1
  happy-path-only: 3
  other: 0

Claim Ledger:
  supported: ~25 (majority of API endpoints, auth flow, vault system)
  partially_supported: 3
  unsupported: 2
  contradicted: 3
  stealth_change: 0
```

## Critical and High Findings

### CRIT-1: Missing auth dependencies crash app at runtime
- **File:** `backend/requirements.txt`
- **Severity:** CRITICAL
- **Problem:** `auth_service.py` imports `jwt` (PyJWT), `bcrypt`, and uses `passlib` — **none** of these are in `requirements.txt`. A fresh `pip install -r requirements.txt` will produce an app that crashes on any authentication operation. The app cannot register, login, or validate JWT tokens.
- **Fix:** Add `PyJWT>=2.8.0`, `bcrypt>=4.0.0`, `passlib[bcrypt]>=1.7.4` to `requirements.txt`.
- **Evidence:** `auth_service.py:9` `import jwt`, line 45 `import bcrypt`, line 14 `from passlib.context import CryptContext`. `grep -c 'PyJWT\|bcrypt\|passlib' backend/requirements.txt` = 0.

### CRIT-2: Docker container runs as root
- **File:** `Dockerfile`
- **Severity:** CRITICAL (with HIGH confidence given the attack surface of document parsing)
- **Problem:** The Dockerfile has no `USER` directive. The application runs as root, meaning any RCE via document parsing (unstructured.io processes arbitrary user-uploaded files) gives root access inside the container.
- **Fix:** Add `RUN addgroup --system app && adduser --system --ingroup app app` and `USER app` before CMD.

### HIGH-1: Settings endpoints lack admin authorization
- **File:** `backend/app/api/routes/settings.py:410-463`
- **Problem:** `POST /settings` and `PUT /settings` only require `get_current_active_user` — any viewer/member can modify `ollama_chat_url`, `embedding_model`, `maintenance_mode`, etc. Combined with SSRF (redirecting LLM URLs to attacker servers), this is exploitable.
- **Fix:** Add `Depends(require_admin_role)` to both endpoints.

### HIGH-2: Connection test endpoint has no authentication
- **File:** `backend/app/api/routes/settings.py:476-511`
- **Problem:** `GET /settings/connection` makes outbound HTTP requests to configured URLs with zero authentication. Leaks internal infrastructure connectivity status to anyone.
- **Fix:** Add `Depends(require_admin_role)`.

### HIGH-3: Client-supplied X-Scopes header trusted for authorization
- **File:** `backend/app/security.py:146-165`
- **Problem:** `require_scope()` reads scopes from the client-supplied `X-Scopes` header. An attacker with a valid admin token can set any scope they want, making scope-based authz meaningless.
- **Fix:** Derive scopes from authenticated identity, not from request headers.

### HIGH-4: CSRF cookie hardcoded `secure=False`
- **File:** `backend/app/security.py:188`
- **Problem:** CSRF cookie always sent over plain HTTP. The auth routes use `_is_secure_request()` for refresh cookies but CSRF doesn't.
- **Fix:** Use dynamic `secure` flag based on request scheme.

### HIGH-5: SSRF via settings modification
- **File:** `backend/app/api/routes/settings.py:162-174`
- **Problem:** `ollama_embedding_url` and `ollama_chat_url` accept any HTTP URL. Combined with HIGH-1 (any user can modify settings), attackers can redirect LLM calls to internal services (cloud metadata, internal APIs).
- **Fix:** Block private IP ranges, or restrict settings modification to admins.

### HIGH-6: JWT access token persisted to localStorage
- **File:** `frontend/src/stores/useAuthStore.ts:329`
- **Problem:** Zustand persist middleware serializes `accessToken` to `localStorage` under key `auth-storage`. Any XSS payload can steal it. The httpOnly refresh cookie already handles persistence.
- **Fix:** Remove `accessToken` from the `partialize` function.

### HIGH-7: Password change on ProfilePage doesn't send current password
- **File:** `frontend/src/pages/ProfilePage.tsx:68`
- **Problem:** `handleChangePassword` collects `currentPassword` but the API call sends only `{ password: newPassword }`. No server-side verification of current password. A stolen session can silently change the password.
- **Fix:** Include `currentPassword` in the API payload and verify server-side.

### HIGH-8: Race condition on shared mutable state in DocumentRetrievalService
- **File:** `backend/app/services/document_retrieval.py:82`
- **Problem:** `no_match` flag is a mutable instance attribute on a singleton service. Concurrent requests can overwrite each other's flag, producing incorrect "no relevant documents" hints.
- **Fix:** Return `no_match` as part of the return value instead of storing on the instance.

### HIGH-9: Multi-scale chunk_index parsing crashes with ValueError
- **File:** `backend/app/services/document_retrieval.py:235`
- **Problem:** `int(s.metadata.get("chunk_index", 0))` but multi-scale indexing sets `chunk_index` to strings like `"512_3"`. `int("512_3")` raises `ValueError`, crashing window expansion for multi-scale documents.
- **Fix:** Parse the index portion after the scale prefix, or store raw integer separately.

### HIGH-10: SetupPage navigates to /login after successful registration
- **File:** `frontend/src/pages/SetupPage.tsx:75`
- **Problem:** After successful `register()` (which sets auth state), navigates to `/login` instead of `/`. User is already authenticated but gets sent to login, creating a confusing UX loop.
- **Fix:** Navigate to `/` like `RegisterPage.tsx` does.

### HIGH-11: Health check leaks httpx client (connection pool leak)
- **File:** `backend/app/services/llm_health.py:54`
- **Problem:** `check_embeddings()` creates a local `EmbeddingService` with a persistent `httpx.AsyncClient` that is never closed. Each health check call leaks a connection pool.
- **Fix:** Add cleanup in finally block.

### HIGH-12: Chat add_message requires only "read" permission instead of "write"
- **File:** `backend/app/api/routes/chat.py:577`
- **Problem:** `add_message` checks `evaluate_policy(user, "vault", vault_id, "read")` — but adding a message is a write operation. Any user with read access can inject messages into any chat session in that vault.
- **Fix:** Change to `"write"` permission check.

### HIGH-13: Chat sessions not filtered by user_id — cross-user visibility
- **File:** `backend/app/api/routes/chat.py:278-337`
- **Problem:** `list_sessions` and `get_session` never filter by `user_id` despite the `chat_sessions` table having a `user_id` column. Any user with vault read access can see ALL chat sessions and messages from ALL users in that vault.
- **Fix:** Add `WHERE user_id = ?` filter for non-admin users.

### HIGH-14: Insecure defaults in .env.example
- **File:** `.env.example:22,51`
- **Problem:** Ships with `ADMIN_SECRET_TOKEN=admin-secret-token` and `JWT_SECRET_KEY=change-me-to-a-random-64-char-string`. Users who copy without changing get known secrets.
- **Fix:** Set to empty strings with generation instructions.

### HIGH-15: Test with `pass` body hides missing coverage
- **File:** `backend/tests/test_admin_user_management.py:696`
- **Problem:** `test_cannot_deactivate_last_admin_via_other_admin` body is only `pass`. Masks a coverage gap for the last-admin deactivation guard.

### HIGH-16: Default health_check_api_key bypasses all rate limiting
- **File:** `backend/app/config.py:165`
- **Problem:** Default `health_check_api_key = "health-api-key"` is used by the rate limiter whitelist. Anyone who knows this value can bypass login brute-force protection (10/min limit).
- **Fix:** Require explicit setting or use cryptographically random default.

### HIGH-17: Admin password reset doesn't invalidate sessions
- **File:** `backend/app/api/routes/users.py:290-325`
- **Problem:** Resets password but doesn't delete existing `user_sessions`. Victim's existing tokens remain valid up to 15 minutes (access) or 30 days (refresh).
- **Fix:** Delete all `user_sessions` for the target user.

## Medium Findings

### Security (Group 3)
- **SEC-M1:** CSRF token endpoint has no authentication (`settings.py:466`)
- **SEC-M2:** PATCH users endpoint missing CSRF protection (`users.py:205`)
- **SEC-M3:** Session revocation DELETEs missing CSRF protection (`auth.py:573,610`)
- **SEC-M4:** Maintenance middleware fails open when service unavailable (`maintenance.py:33`)
- **SEC-M5:** Internal error details leaked in HTTP responses (`auth.py:96,235,324`)
- **SEC-M6:** Batch delete lacks per-document vault permission check (`documents.py:753`)
- **SEC-M7:** Vault creation has no role restriction — viewers can create vaults (`vaults.py:191`)
- **SEC-M8:** User deactivation doesn't invalidate sessions (`users.py:440`)
- **SEC-M9:** Redis exposed without authentication in docker-compose (`docker-compose.yml:25`)
- **SEC-M10:** Manual CORS preflight handlers with wildcard headers in groups.py (`groups.py:88`)

### Behavior (Group 1)
- **SVC-M1:** Health check mutates shared EmbeddingService timeout without thread safety (`llm_health.py:59`)
- **SVC-M2:** UID deduplication strips scale from multi-scale file IDs (`document_retrieval.py:26`)
- **SVC-M3:** Password whitespace check rejects valid passwords with leading/trailing spaces (`auth_service.py:58`)
- **SVC-M4:** Retrieval evaluator returns CONFIDENT for empty chunks instead of NO_MATCH (`retrieval_evaluator.py:31`)
- **SVC-M5:** Context distiller drops chunks < 50 chars without logging (`context_distiller.py:150`)
- **SVC-M6:** Email service double-close on file descriptor in error path (`email_service.py:567`)
- **SVC-M7:** max_distance_threshold format string crashes if None (`document_retrieval.py:171`)

### Substance/Wiring (Group 2)
- **SVC-M8:** max_context_chunks parameter accepted but never used — dead config (`prompt_builder.py:27`)
- **SVC-M9:** Duplicated format_chunk method in PromptBuilderService and DocumentRetrievalService
- **SVC-M10:** Backward compatibility shim methods in RAGEngine add fragile maintenance burden (`rag_engine.py:610`)

### Dependencies (Group 4)
- **CFG-M1:** `bleach>=6.0.0` is deprecated by Mozilla — recommend `nh3` (`requirements.txt:18`)
- **CFG-M2:** `aioimaplib` is low-signal package — verify intended (`requirements.txt:17`)

### AI Smells (Group 7)
- **SVC-M11:** Token estimation uses len//4 heuristic, fails badly for CJK text (`rag_engine.py:644`)
- **SVC-M12:** Vector store uses inconsistent SQL escaping — backslash vs double-quote (`vector_store.py:698`)
- **SVC-M13:** RerankingService creates new httpx client per call (`reranking.py:120`)
- **SVC-M14:** FTS query applies two separate where() calls — may drop vault filter (`vector_store.py:731`)
- **SVC-M15:** Maintenance set_flag has unbounded retry loop without backoff (`maintenance.py:68`)

### Frontend
- **FE-M1:** MarkdownContent renders without rehype-sanitize (XSS risk) (`MarkdownContent.tsx:84`)
- **FE-M2:** API key auth validates via health check which doesn't require auth (`AuthContext.tsx:34`)
- **FE-M3:** Admin routes lack route-level role guards — flash of unauthorized content (`App.tsx:180`)
- **FE-M4:** Hardcoded fallback vault_id: 1 when no active vault selected (`useSendMessage.ts:46`)
- **FE-M5:** Module-level chat cache persists across user sessions, never cleared on logout (`useChatHistory.ts:10`)
- **FE-M6:** Stale closure in SessionRail fetchSessionDetails effect (`SessionRail.tsx:699`)
- **FE-M7:** Auth init() doesn't attempt refresh when accessToken is null (`useAuthStore.ts:118`)
- **FE-M8:** Dual auth system (AuthContext + useAuthStore) creates overly permissive OR-based auth (`ProtectedRoute.tsx:14`)

### Infrastructure/Config
- **CFG-M3:** docker-compose.override.yml auto-applies, bypassing build (`docker-compose.override.yml:3`)
- **CFG-M4:** Hardcoded user-specific Windows paths in start-services.ps1 (`start-services.ps1:10`)
- **CFG-M5:** stop-services.ps1 kills ALL node/python processes system-wide (`stop-services.ps1:6`)
- **CFG-M6:** Dockerfile copies backend/app but not scripts or migration files (`Dockerfile:30`)
- **CFG-M7:** Email service shutdown doesn't await polling task completion (`lifespan.py:312`)
- **CFG-M8:** Circuit breaker only on OpenAI model check, not Ollama (`model_checker.py:196`)
- **CFG-M9:** Tri-vector mode overwrites embeddings_url, breaking fallback (`embeddings.py:114`)

### Tests (Group 9)
- **TST-M1:** Adversarial tests assert invalid state is stored instead of rejected (`test_adversarial_security.py:49`)
- **TST-M2:** Test files use manual runners, invisible to pytest (`test_singleton_processor.py:1`)
- **TST-M3:** conftest mutates global settings without cleanup (`tests/conftest.py:17`)
- **TST-M4:** Root conftest stubs entire libraries, hiding import failures (`conftest.py:14`)
- **TST-M5:** Rate limiting tests verify source text, not runtime behavior (`test_auth_rate_limiting.py:24`)
- **TST-M6:** setUp directly mutates global settings singleton (`test_chat_auth.py:119`)

## Low and Info Findings

- **SEC-L1:** CSRF tokens reusable within TTL window, not single-use (`security.py:99`)
- **SEC-L2:** Admin secret token leaked as user_id in require_scope return (`security.py:161`)
- **SEC-L3:** Refresh token returned in response body during registration (`auth.py:133`)
- **SEC-L4:** Hardcoded fallback token in get_current_active_user (`deps.py:148`)
- **SEC-L5:** Table name in PRAGMA via f-string (hardcoded, not exploitable) (`database.py:380`)
- **SVC-L1:** Dead code: circuit breaker callback functions never wired (`circuit_breaker.py:266`)
- **SVC-L2:** Schema parser regex requires trailing semicolon (`schema_parser.py:25`)
- **SVC-L3:** reset_background_processor fire-and-forget task (`background_tasks.py:77`)
- **FE-L1:** Unsafe `as any` cast on register response (`useAuthStore.ts:217`)
- **FE-L2:** Implicit `any` via _retry flag on axios config (`api.ts:132`)
- **FE-L3:** Duplicate reset/resetState methods in settings store (`useSettingsStore.ts:304`)
- **FE-L4:** API functions duplicated locally in AdminGroupsPage (`AdminGroupsPage.tsx:28`)
- **FE-L5:** Logout doesn't clear module-level caches and localStorage artifacts (`useAuthStore.ts:236`)
- **FE-L6:** RegisterPage empty catch block swallows errors (`RegisterPage.tsx:81`)
- **FE-L7:** useEffect with empty deps references closure-captured functions (`AuthContext.tsx:60`)
- **CFG-L1:** Flag-embed Dockerfile uses unpinned local base image (`flag-embed-server/Dockerfile:1`)
- **CFG-L2:** Docker Compose uses host-gateway for flag-embed instead of service networking (`docker-compose.yml:28`)
- **CFG-L3:** backup_sqlite.py uses deprecated datetime.utcnow() (`scripts/backup_sqlite.py:26`)
- **CFG-L4:** F-strings in logging calls bypass lazy evaluation (`flag-embed-server/server.py:27`)
- **CFG-L5:** Vite dev proxy target port (9090) differs from Docker (8080) (`vite.config.ts:18`)
- **CFG-L6:** Dockerfile installs libreoffice adding ~500MB to image (`Dockerfile:13`)
- **TST-L1:** Immutability test does not actually test immutability (`test_citation_and_score_type.py:189`)
- **TST-L2:** Adversarial test catches SystemExit silently (`test_adversarial_security.py:133`)
- **TST-L3:** Whitespace-only admin token doesn't trigger warning — documented as intended (`test_admin_token_warning.py:330`)
- **FE-I1:** TODO-commented-out endpoints for editMessage, regenerateMessage, exportChatSession (`api.ts:930`)

## Dominant AI Failure Modes

1. **happy-path-only** (3 instances): Retrieval evaluator returns CONFIDENT on empty input; token estimation uses naive heuristic; password check rejects valid passwords with whitespace
2. **claim-hallucination** (3 instances): README claims xlsx/pptx support not in allowed_extensions; model defaults contradict actual docker-compose config; clone instructions reference wrong repo
3. **context-rot** (1 instance): Dead callback functions in circuit_breaker.py from a prior API design
4. **unwired-functionality** (1 instance): `max_context_chunks` parameter accepted but never applied

## Unsupported or Contradicted Claims

### CONTRADICTED: README model defaults vs docker-compose defaults
- README says embedding model is `nomic-embed-text`, docker-compose defaults to `bge-m3`
- README says chat model is `qwen2.5:32b`, docker-compose defaults to `qwen3:8b`
- README says `EMBEDDING_DIM=768`, but `bge-m3` produces 1024-dim embeddings
- **Evidence:** `README.md:193-196` vs `docker-compose.yml:18-19`

### CONTRADICTED: README clone instructions reference wrong repo name
- README says `cd RAGAPPv2` but the repo is `ragappv3`
- **Evidence:** `README.md:131`

### UNSUPPORTED: README claims xlsx and pptx support
- README says "docx, xlsx, pptx, pdf, csv, sql, txt" but `config.py:198-214` `allowed_extensions` does NOT include `.xlsx` or `.pptx`
- **Evidence:** `config.py:198-214` — set contains `.docx`, `.pdf`, `.csv`, `.sql`, `.txt` etc. but no `.xlsx`, `.pptx`

### CONTRADICTED: README architecture diagram shows Ollama for embeddings
- README shows `Ollama → nomic-embed-text` but docker-compose uses FlagEmbedding server (`flag-embed:18080`) with `bge-m3`
- **Evidence:** `README.md:49-50` vs `docker-compose.yml:13-14`

## Stealth Changes

No stealth changes identified — all shipped behavior appears to correspond to some documented intent, though documentation accuracy is poor.

## Supply Chain and Dependency Notes

- **CRITICAL:** `PyJWT`, `bcrypt`, `passlib` missing from requirements.txt — app cannot authenticate
- `numpy` imported by vector_store.py but not explicitly declared (likely transitive)
- `bleach>=6.0.0` is deprecated by Mozilla as of Jan 2023 — recommend `nh3`
- `aioimaplib` is legitimate but low-download-count package — verified on PyPI
- All other Python dependencies (`fastapi`, `uvicorn`, `httpx`, `pydantic`, `lancedb`, `pyarrow`, `pybreaker`, `unstructured`, `aiofiles`, `python-magic`, `slowapi`, `redis`, `sentence-transformers`, `cryptography`) are well-known, high-trust packages
- Frontend npm dependencies are all mainstream packages from verified publishers

## Coverage Notes

- Database agent and claims verification agent were still running at report time — additional findings may surface from those scopes
- Frontend test files were read but individual test assertion quality was not deeply evaluated per-test
- LanceDB filter expression injection (vector_store.py) marked MEDIUM confidence due to uncertainty about LanceDB's filter parser behavior
- IMAP email ingestion service was read but not tested end-to-end (requires IMAP server)
- The `redesign/` directory was not deeply audited as it appears to be non-shipped design artifacts

## Recommended Remediation Order

1. **Supply chain & auth crash** — Add missing PyJWT/bcrypt/passlib to requirements.txt (CRIT-1)
2. **Docker security** — Add non-root USER directive to Dockerfile (CRIT-2)
3. **Authorization fixes** — Add admin role checks to settings endpoints (HIGH-1, HIGH-2), fix chat permission checks (HIGH-12, HIGH-13), fix X-Scopes trust (HIGH-3)
4. **SSRF prevention** — Block private IP ranges in URL settings (HIGH-5)
5. **Frontend security** — Remove JWT from localStorage (HIGH-6), add rehype-sanitize to MarkdownContent (FE-M1), fix password change flow (HIGH-7)
6. **Secret defaults** — Fix .env.example (HIGH-14), randomize health_check_api_key default (HIGH-16)
7. **Session invalidation** — Invalidate sessions on password reset and user deactivation (HIGH-17, SEC-M8)
8. **Doc accuracy** — Fix README model defaults, clone instructions, file format claims
9. **Race conditions** — Fix singleton mutable state in DocumentRetrievalService (HIGH-8)
10. **Test quality** — Implement pass-body tests, fix global state mutation in test setup, consolidate stubs
