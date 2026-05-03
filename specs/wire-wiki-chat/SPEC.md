# Wiki/Knowledge Compiler Chat Integration

## Problem Statement

Users need access to compiled wiki knowledge during chat interactions. The RAG pipeline currently retrieves evidence from raw documents and user memories, but lacks integration with the wiki system for higher-fidelity, structured domain knowledge. Wiki sources offer:
- Curated, structured claims with explicit status (verified, draft, stale)
- Cross-referenced entity relationships and predicate-aware linking
- Confidence scoring and provenance tracking at claim granularity
- Higher freshness through asynchronous compilation workflows

This feature wires the wiki system end-to-end: retrieval in the backend RAG pipeline, citation throughout the chat interface, and conversation-scoped export with evidence provenance.

## Goals

- [x] Wiki claims enter the RAG pipeline before raw document retrieval (wiki-first ranking)
- [x] Wiki evidence flows through SSE stream with `[W#]` citation labels (distinct from `[S#]` and `[M#]`)
- [x] Frontend renders wiki cards in chat with title, claim, status, confidence, provenance
- [x] RightPane displays wiki-specific evidence tab (conditional on presence)
- [x] Chat export includes W/S/M appendices with complete evidence lineage
- [x] No debug stubs; fallback sources removed (uncited sources hidden)
- [x] Full E2E test coverage: 1092 frontend tests + 19 backend tests

## Non-Goals

- Wiki editing or compilation UI (trigger and workflow defined, execution asynchronous)
- Public wiki page frontend (deferred to separate wiki-viewer feature)
- Real-time cache invalidation (compile job uses existing TTL model)

## Scope

### Backend

**New Module: WikiRetrievalService**
- FTS-based claim retrieval from wiki tables
- Stop-word normalization (strips common articles/prepositions, preserves ALL-CAPS acronyms)
- Predicate-aware relation lookup (matches question intent to entity relationships)
- Split page_status / claim_status for independent assertion health tracking
- Graceful empty fallback when wiki tables are absent
- Synchronous API (called via `asyncio.to_thread` in RAG engine)

**RAGEngine Integration**
- Query classifier gates wiki retrieval (detect entity-heavy queries)
- wiki_used list flows through SSE done event alongside sources + memories
- Three independent citation namespaces: [S#] (documents), [M#] (memories), [W#] (wiki)

**PromptBuilder**
- `format_wiki_evidence()` builds [W#]-labeled context block
- System prompt explains three separate label spaces
- Fallback to page_status when claim_status is null

**CitationValidator**
- Validates [W#] refs from wiki_used list
- Backward compatible with [S#] / [M#] / legacy formats

**Persistence & Export**
- wiki_refs JSON column on chat_messages (PRAGMA-guarded for backward compat)
- Background wiki-compile job enqueued after each answered turn
- Messages fork wiki_refs when duplicating sessions
- Load wiki_refs on session fetch and return in message DTO

**DB Migration**
- Add wiki_refs TEXT column to chat_messages
- Add input_json column to wiki_compile_jobs
- Update rag_trace table with wiki path fields

### Frontend

**Types & State**
- WikiReference TS interface (mirrors WikiEvidence.to_dict)
- Message.wikiRefs in chat store (optional, loaded from backend)
- useLastCompletedAssistantWikiRefs selector for RightPane conditional rendering

**Components**
- WikiCard: indigo-scheme evidence card with claim text, status, confidence %, provenance, external link button
- WikiCards wrapper: "Wiki knowledge:" header, conditional rendering when wikiRefs present
- Extended MarkdownMessage: [W#] citation chip parsing (indigo buttons, distinct from [M#] amber)

**Chat Integration**
- AssistantMessage: wiki cards rendered before source cards; **critical:** uncited sources no longer appear (fallback removed)
- RightPane: conditional "wiki" tab (only when lastCompletedAssistantWikiRefs present); dynamic TabsList grid (3 or 4 cols)
- ChatShell export: W/S/M appendix sections per assistant turn

**SSE & Streaming**
- onWiki callback in ChatStreamCallbacks
- parseSSEStream triggers onWiki when wiki_used array arrives in done event
- useSendMessage accumulates wiki_refs during stream and persists with message

## Acceptance Criteria

### Backend
- [ ] WikiRetrievalService instantiated in lifespan.py and injected into RAGEngine
- [ ] Query classifier routes entity-heavy queries to wiki retrieval before document RAG
- [ ] wiki_used list populated in SSE done event when wiki claims retrieved
- [ ] [W#] citations validate and flow through citation_validator
- [ ] PromptBuilder formats wiki evidence with [W#] labels
- [ ] wiki_refs persisted per message (column created via migration)
- [ ] Messages load wiki_refs from DB; fork correctly on session duplication
- [ ] Background compile job enqueued post-answer with input metadata
- [ ] Tests: normalize_fts_query, extract_query_intent, WikiEvidence.to_dict, retrieve() for empty/null vault

### Frontend
- [ ] WikiReference type exported and used throughout
- [ ] onWiki callback invoked when SSE wiki_used array arrives
- [ ] useSendMessage accumulates and persists wiki_refs
- [ ] WikiCards component renders title, claim_text/excerpt, status, confidence, provenance, external link
- [ ] [W#] citations parsed and rendered as indigo chips
- [ ] AssistantMessage shows wiki cards before source cards
- [ ] **Uncited sources do not appear** (fallback removed; only citedSources shown)
- [ ] RightPane shows "wiki" tab only when wikiRefs present (conditional rendering)
- [ ] RightPane TabsList grid adapts: 3 cols (S/M/preview) or 4 cols (S/M/wiki/preview)
- [ ] ChatShell export builds W/S/M appendix per assistant message
- [ ] Tests: 1092 frontend tests pass (including 37 AssistantMessage + 19 WikiCards new tests)

### Integration
- [ ] No debug stubs (no `[DEBUG-WIKI]` markers or stub implementations)
- [ ] Backward compat: old sessions without wiki_refs load cleanly
- [ ] PR body documents architecture, changes, risks, and manual QA results

## Technical Design

### Data Flow

```
User Query → RAGEngine
  ├─ QueryClassifier: Is this entity-heavy? → Route to WikiRetrievalService
  ├─ WikiRetrievalService: FTS claim search + relation lookup → [W#] evidence
  ├─ Fallback: RawDocumentRAG if no wiki matches → [S#] evidence
  ├─ MemoryStore: Durable user context → [M#] evidence
  └─ PromptBuilder: Format all three with labels → LLM context
      ↓
LLM Answer + Citations
  └─ SSE Stream:
      ├─ Streamed answer text
      ├─ Done event: wiki_used[], sources[], memories[]
      └─ Frontend callback dispatch (onWiki, onSources, onMemories)
```

### Citation Namespaces

Three independent label spaces, each 1-indexed:
- **[S#]:** Document sources (RAG retrieval)
- **[M#]:** Memory records (user context)
- **[W#]:** Wiki claims (compiled knowledge)

Example: `According to [W1], which cites [S2], the [M1]-preferred approach is…` uses all three namespaces in one answer.

### Status & Confidence Tracking

- **WikiEvidence.claim_status** (if set): takes precedence (e.g., "verified", "active")
- **WikiEvidence.page_status** (fallback): used when claim_status is null
- **Combined .status field** in to_dict(): claim_status OR page_status (for UI rendering)
- **Confidence**: numeric (0–1), displayed as percentage (e.g., 87%)

### Backward Compatibility

- `wiki_refs` column on chat_messages is optional — old messages have NULL
- Message DTO returns `wiki_refs: undefined` when column absent (frontend handles gracefully)
- RightPane tab only renders when wikiRefs array is present and non-empty

## Test Plan

### Backend Tests

**test_wiki_retrieval.py** (16 tests)
- normalize_fts_query: stop word stripping, acronym preservation, FTS operator escaping, empty input
- extract_query_intent: entity extraction, predicate terms, empty input
- WikiEvidence.to_dict(): wiki_label field, status precedence, split page/claim status
- WikiRetrievalService: null vault returns [], empty DB graceful handling

**test_prompt_builder_memory_labels.py** (updated)
- Memory labels get [M#]; system prompt explains separate namespaces

### Frontend Tests

**AssistantMessage.test.tsx** (37 tests, 7 fixed)
- Fallback removal: evidence strip renders only for cited sources (7 tests needed [S#] citations added to content)
- MarkdownMessage integration: citation parsing, chip rendering
- Action buttons and state management

**WikiCards.test.tsx** (19 new tests)
- WikiCard rendering: label, title, page_type, confidence, status, claim text/excerpt
- Expand/collapse for long bodies
- Provenance summary display
- External link button behavior
- WikiCards wrapper: empty list handling, multiple cards

**RightPane.test.tsx** (3 test files, mocks updated)
- Conditional wiki tab rendering when wikiRefs present
- TabsList grid columns (3 vs 4) based on hasWikiRefs

**Full suite:** 1092 tests pass (including all new + updated tests)

### Manual QA Checklist

- [ ] Chat with wiki-heavy query: wiki cards appear in AssistantMessage
- [ ] [W#] citations are rendered inline; clicking them opens RightPane to "wiki" tab
- [ ] Export chat: W/S/M appendix appears with correct formatting and evidence summary
- [ ] Old chat session without wiki_refs: loads without errors
- [ ] Source cards appear only for [S#]-cited sources (no uncited fallback)
- [ ] Memory cards appear only for [M#]-cited memories
- [ ] RightPane shows 4 tabs when wiki evidence present; 3 when absent

## Quality Gates

- **TypeScript:** `npx tsc --noEmit` — clean
- **Tests:** `npm run test:unit` → 1092 tests pass
- **Lint:** `npm run lint` → clean
- **Build:** `npm run build` → production build succeeds (bundle size warnings pre-existing)
- **Backend pytest:** `python3 -m pytest tests/test_wiki_retrieval.py tests/test_prompt_builder_memory_labels.py -v` → 19 tests pass

## Risks & Mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| Wiki tables absent (legacy DB) | Medium | Graceful empty return; column-detection PRAGMA; backward compat tests |
| Query classifier misfires | Medium | Falls back to document RAG if wiki returns empty; combined ranking picks best evidence |
| Uncited sources still appear | Low | Fallback removed; only citedSources shown; test assertions verify this |
| Slow wiki queries during chat | Low | FTS is fast; async background job doesn't block answer streaming |
| [W#] label collisions with future features | Very Low | Three namespaces are disjoint; extensible to [C#] or others without conflict |

## Implementation Status

**✅ Complete**
- All backend services and integration
- Frontend components and state management
- Database migration
- Tests (1092 frontend + 19 backend)
- TypeScript typecheck clean
- Production build green

**Remaining:**
- PR creation and CI/CD verification
- Reviewer feedback resolution (if any)
