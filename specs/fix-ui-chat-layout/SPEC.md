# Fix Chat UI Layout Issues

## Problem Statement

Three critical UI/UX issues were identified in the RAG chat application:

1. **Desktop UI dimming on "View All Sources"** — When clicking the "View All" button to open the full sources list, the desktop view darkens unexpectedly, making it difficult to interact with other UI elements.

2. **All sources showing as "Tangential"** — The relevance classification system displays every source as "Tangential" regardless of actual relevance score, providing no meaningful signal to users about source importance.

3. **Citation chips breaking chat prose** — Inline source citations in chat messages render as full filename pills, breaking text flow and causing awkward layout. Additionally, clicking a citation chip should scroll to and highlight the corresponding source in the sidebar.

## Acceptance Criteria

### 1. Desktop UI dimming is fixed
- **Scenario:** User opens chat, clicks "View All" to display full sources list on desktop
- **Expected:** Right sidebar overlay appears without darkening the desktop background
- **Test:** Visual inspection on lg viewport (≥1024px width)

### 2. Sources show correct relevance labels
- **Scenario:** Chat generates response with multiple sources of varying relevance scores
- **Expected:** Sources display correct labels (e.g., "Relevant," "Somewhat Relevant," "Tangential") based on actual score_type and scoring values
- **Test:** 
  - Backend emits score_type in done chunk
  - Frontend correctly maps score to label across distance, rerank, and rrf score types
  - All sources show labels other than "Tangential"

### 3. Citation chips render inline without breaking prose
- **Scenario:** User reads chat message with inline citations
- **Expected:** 
  - Citations render as compact numeric pills (e.g., "[1]") in prose context
  - Touch targets meet WCAG minimum (24x24 on touch devices, 44x44 recommended)
  - Clicking citation pill scrolls source list to highlight the matching source
  - Source sidebar remains open after clicking
- **Test:**
  - Visual inspection of chat message rendering
  - Touch target size validation (28x28 on coarse pointers)
  - Scroll behavior test: click citation → source scrolls into view and highlights
  - List virtualization support for >20 sources

## Technical Design

### 1. Portal visibility fix (ChatShell.tsx)
- Added `useIsMobile()` hook that detects viewport breakpoints via media query
- Gate right-pane sheet mounting on `isBelowLg` flag
- Prevents Radix portal from rendering overlays when DOM cascade doesn't support them
- Left SessionRail intentionally NOT gated (preserves mobile state control)

### 2. Score type propagation (backend + frontend)
**Backend (chat.py):**
- ChatResponse model includes `score_type: str = "distance"` field
- stream_chat_response: captures score_type from done chunk, defaults to "distance"
- non_stream_chat_response: passes score_type to ChatResponse constructor
- Error branches ensure done event always includes score_type

**Frontend (lib/api.ts):**
- SSE enrichment logic maps every source with score_type
- Default to "distance" when missing: `score_type ?? "distance"`
- Unconditionally enriches all sources

### 3. Citation rendering and interaction (AssistantMessage.tsx, RightPane.tsx)
**AssistantMessage.tsx:**
- CitationChip now accepts `variant?: "strip" | "inline"` prop
- Inline variant: compact number-only pill (22x22 base, 28x28 on coarse pointers)
- Strip variant: original full filename chip with FileText icon
- renderContent passes `variant="inline"` to inline citations
- Aria-label preserved for accessibility

**RightPane.tsx:**
- Added stable anchor IDs to SourceListItem buttons: `id={`evidence-source-${source.id}`}`
- Scroll-to-source effect handles both non-virtualized (≤20) and virtualized (>20) paths
- For virtualized: calls scrollToIndex first, then uses requestAnimationFrame + scrollIntoView
- Non-virtualized: uses setTimeout then scrollIntoView

### 4. Test infrastructure fixes
**conftest.py:**
- Made pyarrow stub conditional (only when real install unavailable)
- Stub includes `__version__` to satisfy pandas import chain

**deps.py:**
- Re-exported `get_csrf_manager` from app.security
- Fixes pre-existing breakage where settings.py imports from deps.py

## Non-Goals

- Threshold calibration for relevance labels (P2 follow-up in #36)
- Reranking UI improvements beyond fixing "Tangential-only" bug
- Full accessibility audit beyond WCAG touch target minimums

## Testing

### Frontend
- 6 new tests: viewport-based sheet visibility in ChatShell.test.tsx
- Tests for inline numeric pill rendering in AssistantMessage.test.tsx
- Updated tests with matchMediaMatches flag for media query mocking

### Backend
- test_stream_chat_done_event_has_score_type
- test_stream_chat_done_event_score_type_defaults_to_distance
- test_chat_non_streaming_propagates_score_type
- Verified all four code paths (stream w/ score_type, non-stream w/ score_type, stream-default-distance, stream-error-default-distance)

## Deployment Notes

- No database migrations required
- No breaking API changes (score_type is new field with sensible default)
- Backward compatible with clients that don't expect score_type
- Touch target size changes (28x28 on coarse pointers) conform to WCAG AA guidelines
