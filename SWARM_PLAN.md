# PRs 5 & 6 — Frontend API Layer Cleanup + UX Polish (Issue #20)
Swarm: mega
Phase: 1 [COMPLETE] | Updated: 2026-04-17T03:34:15.349Z

---
## Phase 1: PR 5 — Frontend API Layer & CSRF Cleanup [COMPLETE]
- [x] 1.1: Extract and export CSRF utilities from api.ts (COMPLETED) [MEDIUM]
- [x] 1.2: Add timeout to authClient in useAuthStore.ts (COMPLETED) [SMALL]
- [x] 1.3: Remove CSRF logic from useAuthStore.ts (COMPLETED) [MEDIUM]
- [x] 1.4: Migrate CSRF tests to api.csrf.test.ts (COMPLETED) [MEDIUM]

---
## Phase 2: PR 6 — Design Tokens, Focus Ring, Auto-Focus [COMPLETE]
- [x] 2.1: Add --success CSS variable to index.css (COMPLETED) [SMALL]
- [x] 2.2: Replace hardcoded green with success token in components (COMPLETED) [MEDIUM]
- [x] 2.3: Update test assertions for success color (COMPLETED) [SMALL]
- [x] 2.4: Restore focus ring on chat input (COMPLETED) [SMALL]
- [x] 2.5: Add auto-focus to chat input on mount (COMPLETED) [SMALL]

---
## Phase 3: PR 6 — UX Features (Waiting Indicator, Upload Hint, Delete Undo) [COMPLETE]
- [x] 3.1: Add WaitingIndicator with anti-flicker debounce (COMPLETED) [MEDIUM]
- [x] 3.2: Add Max 50 MB badge to upload drop target (COMPLETED) [SMALL]
- [x] 3.3: Implement undo-able document delete (COMPLETED) [MEDIUM]
- [x] 3.4: Final verification — grep checks + test suite (COMPLETED) [SMALL]

---
## Phase 4: Review Council Remediation (F1–F8) [PENDING]
- [ ] 4.1: Fix WaitingIndicator render condition and add scroll-to-bottom on wait. F1 (CRITICAL): At TranscriptPane.tsx line 677, the condition `isWaitingForResponse && messages.length > 0 && messages[messages.length - 1].role === 'assistant'` does NOT check that the last message has empty content. This causes the indicator to render during the ENTIRE streaming session alongside the 'thinking...' text inside AssistantMessage. FIX: Add `messages[messages.length - 1].content === ''` to the condition so the indicator only shows before any content arrives. F3 (MAJOR): Auto-scroll useEffect at line 517-523 depends on [messages, isStreaming, isAtBottom, virtualizer] but NOT on isWaitingForResponse. When the indicator appears after the 100ms debounce, it may be below the viewport fold. FIX: Add a separate useEffect that scrolls to bottom when isWaitingForResponse transitions from false to true. FILE: frontend/src/components/chat/TranscriptPane.tsx [FR-005] [SMALL] [SMALL]
- [ ] 4.2: Constrain CSRF 403 retry to CSRF-specific failures only. F2 (HIGH): The CSRF response interceptor at api.ts lines 87-95 retries ANY 403 response once with a fresh CSRF token. This could replay non-idempotent POST/DELETE requests on authorization or business-rule 403 errors (e.g., 'you do not have permission to delete this resource'). FIX: Only retry if the 403 response has a CSRF-specific indicator. Check if the response body or headers contain a CSRF-related marker (e.g., response.data?.detail contains 'csrf' case-insensitive, or a custom header like X-CSRF-Error). If no such marker exists, do NOT retry — just reject immediately. This prevents replaying requests that failed for legitimate authorization reasons. FILE: frontend/src/lib/api.ts [FR-001, FR-012] [SMALL] [SMALL]
- [ ] 4.3: Add prefers-reduced-motion support to WaitingIndicator. F6 (MAJOR): WaitingIndicator.tsx uses framer-motion JS-based initial/animate/exit transforms (lines 6-9) which are NOT caught by the CSS @media (prefers-reduced-motion: reduce) rule in index.css. The CSS rule catches animate-bounce on the dots but not the framer-motion fade/slide animation. FIX: Import useReducedMotion from framer-motion. When reduced motion is preferred, set initial/animate transforms to empty objects (no transform) while keeping opacity transitions minimal. The CSS media query already handles the bounce animation on the dots. FILE: frontend/src/components/chat/WaitingIndicator.tsx [FR-005] [SMALL] [SMALL]
- [ ] 4.4: Fix optimistic delete cleanup and toast overlap in DocumentsPage.tsx. F7 (MINOR): After successful deleteDocument() API call at line 327, the document ID stays in optimisticallyDeletedIds Set forever (memory leak for component lifetime). FIX: Add cleanup after successful delete: setOptimisticallyDeletedIds(prev => { const next = new Set(prev); next.delete(docId); return next; }). F8 (MINOR): The undo toast (duration 3000ms) and success toast can overlap due to timer imprecision — both fire at roughly the same time. FIX: Call toast.dismiss(toastId) inside the setTimeout callback before the API call to ensure the undo toast is dismissed before the success toast appears. FILE: frontend/src/pages/DocumentsPage.tsx [FR-007] [SMALL] [SMALL]
- [ ] 4.5: Fix register mock format mismatch in useAuthStore.test.ts. F4 (MAJOR): The mock at lines 196-201 returns { data: { access_token: 'jwt123', user: mockUser } } with a nested user object. But the actual register() implementation at useAuthStore.ts line 198 destructures flat fields directly from response.data: const { access_token, id, username: uname, full_name, role, is_active } = response.data. FIX: Update the mock to return flat fields matching the implementation: { data: { access_token: 'jwt123', id: 1, username: 'newuser', full_name: 'New User', role: 'admin', is_active: true } }. The test assertions at lines 206-209 expect state.user to equal mockUser (which has id, username, full_name, role, is_active) — the flat mock will correctly populate these. FILE: frontend/src/stores/useAuthStore.test.ts [FR-011] [SMALL] [SMALL]
- [ ] 4.6: Fix stale color mock in MessageContent.test.tsx. F5 (MAJOR): The vi.mock at line 18-20 returns { text: 'Relevant', color: 'text-green-600' } but relevance.ts now returns 'text-success' after the Phase 2 token replacement. FIX: Update the mock color to 'text-success' to match the current implementation. Alternatively, use vi.importActual to import the real implementation. FILE: frontend/src/components/chat/MessageContent.test.tsx [FR-011, FR-009] [SMALL] [SMALL]
