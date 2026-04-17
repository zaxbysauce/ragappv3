# SPEC: Frontend API Layer Cleanup & UX Polish (Issue #20)

**Feature:** PR 5 — Frontend API Layer & CSRF Cleanup + PR 6 — Frontend UX Polish  
**Source:** [GitHub Issue #20](https://github.com/zaxbysauce/ragappv3/issues/20)  
**Scope:** Enhancement (code quality + user experience)  
**Status:** Implementation complete, ready for commit/PR

---

## Problem Statement

The KnowledgeVault frontend has accumulated technical debt and UX friction across two areas:

1. **API Layer (PR 5):** CSRF token management is duplicated between `lib/api.ts` and `stores/useAuthStore.ts`, creating maintenance risk and inconsistent error-recovery behavior. The axios client lacks a timeout, allowing requests to hang indefinitely.

2. **UX Polish (PR 6):** Users experience several friction points: no visual feedback during SSE streaming startup, hidden upload size limits, irreversible document deletion without undo, inconsistent success color usage, and suppressed focus rings.

---

## Goals

1. Consolidate all CSRF logic into `lib/api.ts` as the single source of truth
2. Add axios timeout to prevent hanging requests
3. Establish a semantic `--success` CSS design token
4. Add "Waiting for response…" indicator during SSE startup
5. Show upload size limit prominently at drop target
6. Implement undo-able document delete with 3-second cancel window
7. Restore focus-visible rings on interactive components
8. Auto-focus chat input on session mount

---

## Requirements & Acceptance Criteria

### PR 5 — API Layer Cleanup

**FR-001: CSRF Single Source of Truth**  
`lib/api.ts` MUST export `ensureCsrfToken()`, `getCsrfToken()`, `resetCsrfToken()`, and `attachCsrfInterceptor()`. All CSRF fetch-deduplication logic lives here exclusively.

**FR-002: Remove Duplicate CSRF from Auth Store**  
`stores/useAuthStore.ts` MUST import CSRF utilities from `lib/api.ts` and remove its own `csrfToken`, `csrfFetchPromise`, and `ensureCsrfToken()` implementations.

**FR-003: Axios Timeout**  
Both `apiClient` and `authClient` MUST have `timeout: 30000` (30 seconds).

**FR-004: CSRF-Specific 403 Retry**  
The response interceptor MUST only retry 403 responses that contain a CSRF-specific marker (e.g., `detail` contains "csrf" case-insensitive). Non-CSRF 403s MUST reject immediately without replay.

**FR-005: Test Coverage**  
CSRF utilities MUST have dedicated tests in `lib/api.csrf.test.ts` covering: token fetch, deduplication, interceptor attachment, and 403 retry logic.

### PR 6 — UX Polish

**FR-006: Semantic Success Color**  
A `--success` CSS variable MUST exist in `index.css` (light: `142 70% 40%`, dark: `142 60% 50%`). All `text-green-500` usages MUST be replaced with `text-success` via Tailwind config.

**FR-007: Waiting Indicator**  
A `WaitingIndicator` component MUST render in `TranscriptPane` when: (a) SSE is active, (b) the last message is from assistant, (c) the last message has empty content. It MUST have a 100ms anti-flicker debounce and support `prefers-reduced-motion`.

**FR-008: Upload Size Hint**  
The document drop target MUST display "Max 50 MB" as a visible badge/hint before file selection.

**FR-009: Undo Document Delete**  
Single document delete MUST show a toast with "Undo" action. The actual API call MUST be delayed by 3 seconds, allowing cancellation. On cancel, the document MUST reappear in the list.

**FR-010: Focus Ring Restoration**  
The chat input textarea MUST have `focus-visible:ring-2 focus-visible:ring-ring` (not `focus-visible:ring-0`).

**FR-011: Auto-Focus Chat Input**  
The chat input MUST auto-focus on session mount via `useEffect` with empty dependency array.

---

## Technical Design

### CSRF Consolidation Architecture

```
lib/api.ts (single source of truth)
├── ensureCsrfToken() — deduplicated fetch with promise caching
├── getCsrfToken() — read cached token
├── resetCsrfToken() — clear cache
└── attachCsrfInterceptor(axiosInstance) — wire request/response interceptors

stores/useAuthStore.ts (consumer)
└── imports { ensureCsrfToken, attachCsrfInterceptor } from "@/lib/api"
```

Two axios instances retained (`apiClient` + `authClient`) to avoid interceptor loops. Only `apiClient` gets CSRF interceptor; `authClient` is used for auth-only endpoints.

### Waiting Indicator Behavior

```
User sends message
→ isWaitingForResponse = true (immediately)
→ 100ms debounce → render WaitingIndicator
→ First SSE token arrives
→ isWaitingForResponse = false
→ WaitingIndicator exits (framer-motion AnimatePresence)
```

### Delete Undo Flow

```
User clicks delete
→ Document hidden optimistically (optimisticallyDeletedIds Set)
→ Toast appears: "Document deleted" + "Undo" button
→ setTimeout(3000ms)
  ├── User clicks "Undo" → cancel timeout, restore document, dismiss toast
  └── Timeout expires → call deleteDocument API, show success toast
```

---

## Files Changed

### Modified
- `frontend/src/lib/api.ts` — CSRF utilities exported, timeout added
- `frontend/src/stores/useAuthStore.ts` — CSRF logic removed, imports from api.ts
- `frontend/src/stores/useAuthStore.test.ts` — mock format fixed, CSRF tests removed
- `frontend/src/index.css` — `--success` CSS variable added
- `frontend/src/tailwind.config.js` — `success` color mapped to CSS variable
- `frontend/src/lib/relevance.ts` — returns `text-success` instead of `text-green-600`
- `frontend/src/components/chat/TranscriptPane.tsx` — WaitingIndicator integrated, auto-focus
- `frontend/src/components/chat/MessageContent.tsx` — copy button visibility fixed
- `frontend/src/components/chat/AssistantMessage.tsx` — `text-success` usage
- `frontend/src/components/shared/CopyButton.tsx` — `text-success` usage
- `frontend/src/components/shared/StatusBadge.tsx` — `text-success` usage
- `frontend/src/components/shared/ConnectionStatusBadges.tsx` — `text-success` usage
- `frontend/src/components/settings/APIKeySettings.tsx` — `text-success` usage
- `frontend/src/components/layout/NavigationRail.tsx` — `text-success` usage
- `frontend/src/pages/DocumentsPage.tsx` — upload hint, undo delete
- `frontend/src/components/chat/MessageContent.test.tsx` — mock color updated
- `frontend/src/components/layout/NavigationRail.test.tsx` — assertions updated
- `frontend/src/components/shared/StatusBadge.test.tsx` — assertions updated

### Deleted
- `frontend/src/stores/useAuthStore.csrf.test.ts` — migrated to `api.csrf.test.ts`

### Created
- `frontend/src/components/chat/WaitingIndicator.tsx` — new component
- `frontend/src/components/chat/TranscriptPane.waitingindicator.test.tsx` — integration tests
- `frontend/src/components/chat/TranscriptPane.waitingindicator-adversarial.test.tsx` — edge case tests
- `frontend/src/lib/api.csrf.test.ts` — CSRF utility tests

---

## Test Plan

1. **Unit tests:** All existing tests pass (280+ tests)
2. **New test files:** 4 new test files covering CSRF, WaitingIndicator
3. **Regression sweep:** Run full test suite after changes
4. **Manual verification:** Test delete undo flow, waiting indicator, focus behavior

---

## Non-Goals

- Bulk delete undo (out of scope — single delete only)
- Backend architecture changes (PR 7 is separate)
- New dependencies (uses existing framer-motion, @tanstack/react-virtual)

---

## Implementation Status

All code changes are complete and tested in the local working tree. Ready to commit and create PR.

---

*Generated for Ship workflow — Phase 1 handoff*
