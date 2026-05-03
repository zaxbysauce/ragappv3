# Fix Chat Overlap, Memory Relevance, and Module Interoperability

## Problem Statement

Three categories of defects existed in the application:

1. **Chat transcript message overlap**: Messages in the chat transcript were visually overlapping, with new messages appearing on top of previous answers and source cards. Root cause: TanStack Virtual's absolute-positioned rows with stale height measurements after streaming, Shiki highlighting, source card rendering, and dynamic content height changes.

2. **Irrelevant memory retrieval and display**: Unrelated memories (e.g., "birds aren't real", "AFOMIS stands for...") were being retrieved, injected into prompts, and displayed under document-grounded answers. Root causes: (a) backend returning weakly-related memories with no relevance threshold, (b) frontend falling back to displaying all `memoriesUsed` when citations didn't match.

3. **Module interoperability gaps**: Nine separate issues across stores, pages, hooks, and APIs that prevented correct vault/document/upload/settings/profile/health workflows.

## Goals

- **Eliminate chat overlap:** Restore layout stability and visual correctness for all message types, dynamic content, and streaming scenarios.
- **Gate irrelevant memory:** Only retrieve and display memories that pass relevance thresholds and are actually cited in the response.
- **Fix module interop:** Ensure vault selection, document search, upload state, reindex detection, memory editing, org/vault display, health checking, and search diagnostics all work correctly end-to-end.

## Requirements

### Part 1: Chat Message Overlap Fix

**Acceptance Criteria:**
- Messages render in normal document flow (no absolute positioning).
- Each message has a `data-message-id` attribute for addressability.
- No message visually overlaps previous content.
- SourceCards expansion does not cause overlaps.
- MemoryCards rendering does not cause overlaps.
- Async code highlighting does not cause overlaps.
- Streaming does not cause overlaps.
- Auto-scroll pauses when user scrolls up, resumes when "New messages" is clicked.
- Citation highlight/jump still works.
- RightPane source selection still works.
- Message actions still work.

**Test Cases:**
- Render 200-message transcript with document flow; assert all data-message-id present.
- Send user message then assistant message with long markdown table + source cards; assert no overlap.
- Expand source card; assert no following message overlaps.
- Render memory cards below answer; assert no overlap.
- Async syntax highlighting completes; assert no overlap.
- Stream long answer, complete, render sources; assert scroll correct.
- User scrolls up during streaming; assert auto-scroll pauses.

### Part 2: Memory Relevance Filtering

**Backend Changes:**
- Add config: `memory_relevance_filter_enabled: bool = True`
- Add config: `memory_dense_min_similarity: float = 0.30`
- Add config: `memory_rrf_min_score: float = 0.005`
- Add config: `memory_context_top_k: int = 3`
- Filter dense search results: only return memories with similarity >= threshold.
- Filter RRF results: only return memories with fused score >= threshold.
- Cap retrieved memories at `context_top_k` before prompt injection.

**Prompt Instruction:**
- "Use memory ONLY when directly relevant to user query or affects response style."
- "Do not mention unrelated memory context."

**Frontend Changes:**
- Display only cited `[M#]` memories in MemoryCards.
- Do not fall back to all `memoriesUsed`.
- If debug mode enabled, show "Memory candidates" separately (not in answer).

**Acceptance Criteria:**
- Memories below relevance threshold are not retrieved.
- Irrelevant memories do not appear in answers.
- Only cited memories are displayed in MemoryCards.
- Weak semantic similarity alone does not cause memory retrieval.

**Test Cases:**
- Document-factual question with strong doc evidence; no unrelated memories displayed.
- Memory-specific question ("Are birds real?"); pass memory through if relevance threshold met.
- Post-stream, memories are only shown if cited in answer.

### Part 3: Module Interoperability Fixes

#### 3.1: Vault Validation
- **Issue:** `activeVaultId` stored in Zustand could be invalid if vault was deleted.
- **Fix:** After `fetchVaults()`, validate stored ID exists; auto-select first vault or null if gone.
- **Test:** Delete vault; reload profile; activeVaultId auto-corrects.

#### 3.2: Server-Side Document Search
- **Issue:** Client-side search was loading all documents then filtering; inefficient.
- **Fix:** Add `search`, `status` parameters to `listDocuments()` endpoint; server-side SQL filtering.
- **Test:** Search for "foo"; only "foo"-matching documents returned from server.

#### 3.3: Double-Fetch Guard
- **Issue:** DocumentsPage `loadData` and search effects both called `fetchDocuments()` on mount.
- **Fix:** Add `isFirstSearchRender` ref guard; skip search effect on first render.
- **Test:** DocumentsPage mounts; only one fetch call made.

#### 3.4: Upload State Machine with Polling
- **Issue:** Upload completed but indexing state unknown; no polling to track completion.
- **Fix:** Add states: pending → uploading → uploaded → indexing → indexed/error.
- **Fix:** After upload, poll `getDocumentStatus()` every 3s until indexed or error.
- **Test:** Upload file; state transitions from pending→uploading→uploaded→indexing→indexed.

#### 3.5: Reindex Detection
- **Issue:** Settings changes that affect embeddings (embedding_model, chunk_size, etc.) didn't signal reindex needed.
- **Fix:** Add `REINDEX_REQUIRED_FIELDS` set; `checkReindexRequired()` method in store.
- **Fix:** After settings save, check if reindex required; show amber banner if so.
- **Test:** Change embedding_model; banner appears after save.

#### 3.6: Memory Edit UI
- **Issue:** No UI to edit/delete memories; only backend support existed.
- **Fix:** Add Dialog in MemoryPage with editable content, category, tags, source fields.
- **Fix:** Add Pencil button to edit; Trash2 button to delete with confirm.
- **Test:** Edit memory; changes persist. Delete memory; confirm dialog works.

#### 3.7: Org/Vault Display
- **Issue:** ProfilePage didn't show user's organizations or accessible vaults.
- **Fix:** Load `listOrganizations()` and `listVaults()` in ProfilePage useEffect.
- **Fix:** Display "Organization Access" card showing memberships.
- **Fix:** Display "Vault Access" card showing accessible vaults with file counts.
- **Test:** ProfilePage renders; both cards display org and vault info.

#### 3.8: Health Hook Mutation Bug
- **Issue:** `useHealthCheck` used object mutation in setState (`prev.lastChecked = ...`).
- **Fix:** Create new state object in setState callback.
- **Test:** Health check updates; no mutation warnings.

#### 3.9: Search Response Label
- **Issue:** DocumentsPage search results had no label differentiating from other views.
- **Fix:** Add `search_type: str = "diagnostic"` field to SearchResponse.
- **Test:** Search response includes search_type field.

#### 3.10: Backend Vault Response
- **Issue:** Frontend needed to know which vault is default (id=1).
- **Fix:** Add `is_default: bool = False` to VaultResponse; set based on vault_id.
- **Test:** Vault response includes is_default field; matches vault_id == 1.

**Acceptance Criteria:**
- All module workflows (vault selection, document search, upload state, reindex, memory edit, org/vault display, health checks) work end-to-end.
- No unrelated memories appear in document answers.
- Settings changes that affect embeddings are detected and communicated.
- Upload state transitions correctly with polling.
- ProfilePage shows user's organizations and accessible vaults.

## Technical Design

### Chat Overflow Fix: Document Flow Replacement

Replace TanStack Virtual's absolute-positioned rows with normal document flow:

```tsx
// Before: virtual rows at top: vItem.start
<div style={{ top: vItem.start, position: 'absolute' }}>
  <Message ... />
</div>

// After: normal block layout
<div data-message-id={messageId}>
  <Message ... />
</div>
```

Auto-scroll via `Element.scrollTo()`:

```tsx
const scrollToBottomNow = (behavior = 'auto') => {
  const el = scrollContainerRef.current;
  if (el) {
    el.scrollTo({ top: el.scrollHeight, behavior });
  }
};
```

Track scroll state with refs:
- `isAtBottomRef`: whether currently scrolled to bottom
- `userScrolledUpRef`: whether user manually scrolled up (pauses auto-scroll)

Token-growth auto-scroll effect:

```tsx
useEffect(() => {
  const contentLen = useStreamingMessageContentLength();
  if (contentLen > 0 && isAtBottomRef.current && !userScrolledUpRef.current) {
    scrollToBottomNow();
  }
}, [useStreamingMessageContentLength()]);
```

### Memory Relevance Filtering

Backend thresholds filter weak candidates before returning to prompt builder:

```python
# config.py
memory_dense_min_similarity: float = 0.30
memory_rrf_min_score: float = 0.005
memory_context_top_k: int = 3

# memory_store.py — dense search
if sim < settings.memory_dense_min_similarity:
  skip_candidate()

# memory_store.py — RRF search
if rrf_score < settings.memory_rrf_min_score:
  skip_candidate()

# rag_engine.py
memories = memories[:settings.memory_context_top_k]
```

Frontend only shows cited memories:

```tsx
const citedMemories = /* extract [M#] from response */;
const memoriesForCards = citedMemories; // no fallback to all memoriesUsed
```

### Module Interop: Distributed Fixes

Each fix is isolated and targeted:

- **Vault validation:** `useVaultStore.fetchVaults()` validates activeVaultId after fetch.
- **Search:** `listDocuments()` accepts `search` param; server filters via `LOWER(file_name) LIKE ?`.
- **Double-fetch:** DocumentsPage adds `isFirstSearchRender` ref guard.
- **Upload polling:** `useUploadStore.processQueue()` transitions to indexing, polls status.
- **Reindex detection:** `useSettingsStore.checkReindexRequired()` checks against `REINDEX_REQUIRED_FIELDS`.
- **Memory edit:** MemoryPage Dialog with edit/delete buttons.
- **Org/vault display:** ProfilePage `useEffect` loads org and vault data.
- **Health mutation:** `useHealthCheck` setState creates new object.
- **Search label:** SearchResponse includes `search_type` field.
- **Vault response:** VaultResponse includes `is_default` field.

## Non-Goals

- Implement lazy loading/pagination for large transcripts (future work; normal flow is sufficient now).
- Implement memory reranking or LLM grading (threshold filtering is sufficient).
- Implement per-memory citation/evidence (fallback to all memoriesUsed is removed; only cited memories shown).
- Implement fine-grained memory filtering by category/source (top_k cap is sufficient).

## Success Criteria (Exit Gate)

- [ ] All 1058 existing tests pass.
- [ ] Typecheck clean (no TypeScript errors).
- [ ] Build succeeds.
- [ ] Chat transcript displays without overlap in all scenarios (streaming, source cards, memory cards, code highlighting).
- [ ] Memory filtering gates irrelevant memories; only relevant memories retrieved.
- [ ] All module workflows (vault, document, upload, settings, memory, profile, health, search) work end-to-end.
- [ ] No unrelated memories appear in document-grounded answers.
- [ ] Settings changes affecting embeddings are detected and communicated.
- [ ] PR is created, tested, reviewed, and merged.

## Out of Scope

- Implement virtual scrolling with proper RemeasureObserver (use document flow instead).
- Implement memory reranking (threshold filtering sufficient).
- Implement pagination for large chats (document flow is sufficient).

## Test Coverage

- Unit tests for each module: store updates, hook behavior, API calls.
- Integration tests for workflows: vault selection → document fetch, upload → indexing, settings change → reindex detection.
- Adversarial tests for edge cases: 200+ message transcript rendering, overlapping dynamic content, memory threshold boundaries.
- Playwright tests for chat overlap (layout stability across all scenarios).

---

## Implementation Status

- **Phase 2: Complete** — All code changes committed to branch `claude/fix-chat-overlap-virtual-KVBQX`
- **Quality gates: Pass** — 1058 tests pass, typecheck clean, build succeeds
- **PR: Pending** — Draft PR to be created
- **Phase 3-6: Pending** — QA, docs, review, completion

## Change Summary

**Modified Files: ~35**

- Backend: config.py, memory_store.py, rag_engine.py, prompt_builder.py, vaults.py, documents.py, search.py
- Frontend: TranscriptPane.tsx, AssistantMessage.tsx, useChatStore.ts, useVaultStore.ts, useUploadStore.ts, useSettingsStore.ts, useHealthCheck.ts, DocumentsPage.tsx, MemoryPage.tsx, SettingsPage.tsx, VaultsPage.tsx, ProfilePage.tsx, api.ts, test files
- Tests: 12 test files updated/created

**Commits: 1**
- `9f711e6 Fix chat overlap, memory relevance, and module interoperability`

---

## Review Checklist (Phase 5)

- [ ] Chat transcript rendering without overlap (visual verification)
- [ ] Memory filtering gates irrelevant memories (integration test)
- [ ] Module workflows all functional (end-to-end verification)
- [ ] No regression in existing features
- [ ] Documentation updated
- [ ] All CI checks pass
