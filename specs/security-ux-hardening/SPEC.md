# Security Hardening & UX Improvements

## Problem Statement

A security audit of ragappv3 identified two classes of issues:

1. **Prompt injection (CWE-1333):** All user-controlled content — document chunks, memory records, user queries, and chat history — entered LLM prompts without structural isolation. A malicious document or query could embed instructions that override system behavior. Additionally, no role allowlist existed on the chat message API, allowing arbitrary role values (`"system"`, `"admin"`, etc.) to be injected into conversations.

2. **Auth/UX friction:** Registration errors were silently swallowed (empty `catch` blocks), authenticated users were redirected to `/login` instead of `/`, password fields had no visibility toggle, the mobile nav omitted Profile and Organizations, the login loading state was unbranded, and chat exports lost markdown structure.

## Goals

- Structural isolation of all untrusted content before LLM injection (defense-in-depth against prompt injection)
- Role allowlist enforcement at the API model layer
- Verified test coverage for all injection defenses
- Improved registration/login UX with visible errors, password toggles, and correct redirects
- Magic byte validation on document upload (prevent extension spoofing)
- Chat export preserves markdown formatting

## Non-Goals

- Complete elimination of all prompt injection risk (XML tags are defense-in-depth, not an absolute guarantee)
- Re-authentication for sensitive settings changes (T11-L6) — deferred
- Inline memory edit (T11-L2) — deferred
- Session expiry warning toast (T11-L3) — deferred
- Vault creation limit messaging (T11-L5) — no backend limit exists

## Technical Design

### Backend: XML Content Boundaries

All untrusted content is wrapped in named XML tags before LLM injection. Tags establish a structural boundary the system prompt instructs the LLM to treat as data-only.

| Tag | Content | Location |
|---|---|---|
| `<document>` | Retrieved document chunk text | `PromptBuilderService.format_chunk()` |
| `<memory>` | User memory record content | `PromptBuilderService.build_messages()` |
| `<user_query>` | User's search query | `QueryTransformer.transform()`, `QueryTransformer.generate_hyde()`, `RetrievalEvaluator.evaluate()` |
| `<user_message>` | First message used for title generation | `_auto_name_session()` in `chat.py` |
| `<source_passages>` | Synthesis source passages | `ContextDistiller._synthesize()` |

### Backend: Role Allowlist

`ChatMessage` and `AddMessageRequest` Pydantic models use `Literal["user", "assistant"]` for the `role` field. Pydantic v2 rejects any other value at deserialization with `ValidationError`.

### Backend: SECURITY BOUNDARY System Prompt Directive

`PromptBuilderService._default_system_prompt()` and `ContextDistiller._SYNTHESIS_PROMPT_SYSTEM` both include an explicit "SECURITY BOUNDARY" paragraph listing all trusted XML tags and instructing the LLM never to follow instructions within them.

### Backend: Title Generation Safety

`_auto_name_session()` wraps the prompt text in `<user_message>` tags and uses `"New conversation"` as fallback (never raw user content prefix). The `add_message()` no-LLM fallback also uses `"New conversation"`.

### Backend: Magic Byte Validation on Upload

`_do_upload()` reads the first 8 bytes of the uploaded file before writing to disk and validates against known magic signatures:
- `.pdf` → `%PDF`
- `.docx`, `.xlsx` → `PK\x03\x04` (ZIP)
- `.xls` → `\xd0\xcf\x11\xe0` (OLE)

Text-based formats (`.txt`, `.md`, `.csv`, `.json`, `.yaml`, etc.) have no fixed binary header and are excluded from magic byte checks.

### Frontend: Auth UX

- Password visibility toggle (Eye/EyeOff from lucide-react) on LoginPage, RegisterPage, SetupPage
- RegisterPage: `<Navigate to="/" replace />` when already authenticated (was `/login`)
- RegisterPage + SetupPage: `catch (err)` surfaces error in UI via local `error` state + `role="alert"` paragraph; 409 → "Username already registered"
- RegisterPage: Live password requirements checklist (8+ chars, 1 digit, 1 uppercase) matching backend `password_strength_check()`
- MobileBottomNav: Profile and Organizations added to "More" drawer
- LoginPage: Branded loading state with `text-primary` spinner and "Loading KnowledgeVault…" label
- ChatShell: Export as `.md` with `text/markdown` MIME type; messages formatted with `### User`/`### Assistant` headers and `---` separators

## Acceptance Criteria

### Security

- [x] `ChatMessage(role="system", content="...")` raises `ValidationError`
- [x] `ChatMessage(role="admin", content="...")` raises `ValidationError`
- [x] `ChatMessage(role="user", content="hello")` succeeds
- [x] `ChatMessage(role="assistant", content="hi")` succeeds
- [x] `AddMessageRequest(role="system", ...)` raises `ValidationError`
- [x] `AddMessageRequest(role="tool", ...)` raises `ValidationError`
- [x] `format_chunk(chunk, 1)` output contains `<document>{text}</document>`
- [x] Injection payload in chunk text appears only within `<document>` tags, never outside
- [x] `build_messages(...)` with chunk produces `<document>` and `</document>` in user message
- [x] `build_messages(...)` with memory produces `<memory>{content}</memory>` in user message
- [x] Injection payload in memory appears only within `<memory>` tags
- [x] `build_system_prompt()` contains "SECURITY BOUNDARY", "untrusted external data", `<document>`, `<memory>`
- [x] First message in `build_messages(...)` has `role == "system"` and contains "SECURITY BOUNDARY"

### Upload Validation

- [x] File with `.pdf` extension but non-PDF magic bytes → HTTP 400
- [x] Empty file → HTTP 400
- [x] Valid PDF with correct magic bytes → accepted

### Frontend UX

- [x] Password field on LoginPage shows Eye/EyeOff toggle; clicking reveals/hides password
- [x] RegisterPage: authenticated user redirects to `/`, not `/login`
- [x] RegisterPage: API error on submit is displayed (not swallowed)
- [x] RegisterPage: password requirements appear live as user types
- [x] MobileBottomNav "More" drawer contains Profile and Organizations entries
- [x] LoginPage loading shows branded spinner with app label
- [x] Chat export produces `.md` file with markdown section headers

## Test Plan

### Automated (backend)

`backend/tests/test_prompt_injection.py` — 15 tests across 4 test classes:
- `TestRoleAllowlist` (8 tests): role validation on both Pydantic models
- `TestChunkXMLBoundary` (3 tests): document chunk wrapping in format_chunk and build_messages
- `TestMemoryXMLBoundary` (2 tests): memory content wrapping in build_messages
- `TestSystemPromptSecurityDirective` (2 tests): SECURITY BOUNDARY directive presence

### Manual (frontend)

| Scenario | Steps | Expected |
|---|---|---|
| Password visibility | Click Eye icon on Login/Register/Setup password field | Input type toggles text/password |
| Register error display | Submit registration with duplicate username | Error message appears below form |
| Register redirect | Log in, navigate to /register | Redirected to / |
| Password requirements | Type progressively stronger password in Register | Requirements turn green as met |
| Mobile nav | Open mobile "More" drawer | Profile and Organizations visible |
| Login loading | Visit /login with slow network | Branded spinner with label |
| Chat export | Have conversation, click export | Downloads .md file with markdown headers |

## Files Changed

### Backend
- `backend/app/api/routes/chat.py` — role Literal type, XML-wrapped title generation, safe fallback
- `backend/app/api/routes/documents.py` — magic byte validation on upload
- `backend/app/services/context_distiller.py` — SECURITY BOUNDARY directive, XML-wrapped synthesis inputs
- `backend/app/services/prompt_builder.py` — SECURITY BOUNDARY directive, `<document>` and `<memory>` wrapping
- `backend/app/services/query_transformer.py` — `<user_query>` wrapping for step-back and HyDE
- `backend/app/services/retrieval_evaluator.py` — `<user_query>` wrapping
- `backend/tests/test_prompt_injection.py` — new: 15-test prompt injection test suite

### Frontend
- `frontend/src/components/layout/MobileBottomNav.tsx` — Profile + Organizations in More drawer
- `frontend/src/pages/ChatShell.tsx` — markdown export
- `frontend/src/pages/LoginPage.tsx` — Eye/EyeOff toggle, branded loading state
- `frontend/src/pages/RegisterPage.tsx` — error display, correct redirect, password requirements, Eye/EyeOff
- `frontend/src/pages/SetupPage.tsx` — error display, Eye/EyeOff
