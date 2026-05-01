# Chat UI/UX Premiumization

## Problem Statement

The active chat interface (`frontend/src/`) had several structural problems preventing a tier-1 commercial AI/RAG experience:

1. **Rendering performance**: `useChatStore` stored `messages: Message[]` and called `updateMessage` by remapping the entire array on every streamed token, causing unnecessary re-renders of all visible messages.
2. **Stale state race**: retry/edit flows set Zustand input state then immediately called `handleSend`, reading stale values due to React's batched updates.
3. **Duplicate event listeners**: `evidence:jump-to-answer` was registered twice in `TranscriptPane`, causing double scroll/highlight on citation clicks.
4. **Duplicated rendering code**: `AssistantMessage.tsx` and `MessageContent.tsx` each owned parallel markdown rendering pipelines with no shared abstraction.
5. **No syntax highlighting**: fenced code blocks rendered as unstyled `<pre>` text.
6. **Visual design**: full-width tinted background bands (`bg-muted/30`, `bg-primary/[0.12]`, `border-l-2`) made the chat look like a system log, not a premium AI interface.
7. **Composer coupling**: Composer logic lived inside `TranscriptPane.tsx` (900+ lines), making the file unmaintainable.
8. **No file attachment support**: paste/drop support was absent despite `uploadDocument()` API and `react-dropzone` being available.
9. **Weak source attribution**: source cards with relevance labels, expand/collapse, and "view all" were missing.
10. **Missing session delete undo**: deleting a session was irreversible with no undo affordance.

## Goals

Make the active chat experience feel like a tier-1 commercial AI/RAG interface while preserving all existing functionality: sessions, vaults, streaming, citations, right evidence pane, source relevance, message feedback, retry/edit/fork/branch, mobile sheets, and route behavior.

## Non-Goals

- Backend changes
- Redesign of the `/redesign` directory (unused)
- Rewriting the vault/documents pages

## Requirements and Acceptance Criteria

### Phase 1: Behavior Bug Fixes

**AC-1.1 — No duplicate evidence jump listener**
- Clicking a citation causes exactly one scroll + highlight cycle
- No duplicate `window.addEventListener("evidence:jump-to-answer", ...)` in `TranscriptPane`

**AC-1.2 — Retry/edit race eliminated**
- `sendDirect(content, history, options)` primitive accepts content and history directly
- Retry sends the intended last user message with trimmed history deterministically
- Edit-resubmit restores correct content and trims downstream messages
- No race from async state updates or rapid double-click

**AC-1.3 — Stop generation preserved**
- Abort clears streaming state and marks message as stopped
- Partial text remains visible; no red error UI for user-initiated abort

### Phase 2: Streaming Performance

**AC-2.1 — Normalized store**
- `useChatStore` exports `messageIds: string[]` and `messagesById: Record<string, Message>`
- `appendToMessage(id, chunk)` mutates only the single streaming message
- Granular selectors: `useMessageIds()`, `useMessage(id)`, `useChatMessages()`, `useChatIsStreaming()`, `useChatStreamingId()`, `useChatInput()`, `useChatInputError()`, `useChatActiveChatId()`

**AC-2.2 — Streaming isolation**
- Non-streaming visible messages do not re-render on every token
- RightPane does not recompute all sources on every token unless source data changed

### Phase 3: Unified Rendering Pipeline

**AC-3.1 — Shared components**
- `MarkdownMessage.tsx`: markdown render, streaming caret, optional citations
- `SourceCitation.tsx`: inline citation chip `[S1]` / `[Source: filename]`
- `SourceCards.tsx`: answer-level source attribution cards
- `MessageActions.tsx`: copy, retry, feedback, fork, debug action bar
- `Composer.tsx`: extracted composer with full feature set

**AC-3.2 — Citation handling**
- `[S1]`, `[S2]` style citations resolved to source filenames
- Legacy `[Source: filename]` handled
- Clicking a citation opens right pane, selects source

**AC-3.3 — Markdown support**
- GFM tables, lists, blockquotes, checklists
- Code blocks with copy button and language label
- Sanitization via `rehype-sanitize`

### Phase 4: Syntax Highlighting

**AC-4.1 — Shiki integration**
- Fenced code blocks render with syntax colors (light/dark themes)
- Lazy-loaded to avoid penalizing first chat load
- Unknown language falls back to unstyled code
- Copy button copies raw code (no fence markers)

### Phase 5: Premium Chat Layout

**AC-5.1 — Visual design**
- No full-width tinted background bands on messages
- Content column max-width: `max-w-[760px]`
- Prose max-width: ~65ch
- Vertical rhythm: 24–32px between message groups
- Hover action bar hidden until hover/focus/coarse pointer

### Phase 6: Premium Composer

**AC-6.1 — Composer features**
- Floating composer with shadow/backdrop
- Auto-growing textarea
- Enter sends, Shift+Enter newline
- IME composition guard (no submit during CJK composition)
- Stop button always clickable during streaming (not inside `pointer-events-none` container)
- Character count, slash command menu, vault indicator retained

### Phase 7: File Attachments

**AC-7.1 — Paste/drop support**
- Paste files into composer triggers real upload to active vault
- Drag/drop onto composer area works
- Attachment tray shows filename, size, progress, remove action
- No active vault → actionable error
- Send blocked until upload completes
- Tests cover paste/drop state, upload success/failure

### Phase 8: Source UX

**AC-8.1 — Source cards**
- "Sources:" header with count
- Top 3 sources shown by default with expand/collapse
- Each card: filename, snippet preview, relevance label
- "View all N sources" opens RightPane
- Clicking a source selects it in RightPane

**AC-8.2 — RightPane**
- Heading renamed from "Details" to "Evidence"
- Tabs preserved: Sources, Preview, Extracted

### Phase 9: Session Rail

**AC-9.1 — Delete undo**
- Session delete shows Sonner toast with Undo action
- Undo restores the session optimistically

**AC-9.2 — Inline rename**
- Optimistic update with revert on failure

### Phase 10–12: Polish

- Message action bar: copy, retry, feedback (thumbs up/down), fork/branch, debug panel
- Typography improvements; Tailwind Typography plugin applied
- Theme-aware code blocks; microinteractions via Framer Motion

## Technical Design

### Store normalization

```typescript
// Before
messages: Message[]
updateMessage: (id, partial) => set(s => ({ messages: s.messages.map(m => m.id === id ? {...m, ...partial} : m) }))

// After
messageIds: string[]
messagesById: Record<string, Message>
appendToMessage: (id, chunk) => set(s => ({
  messagesById: { ...s.messagesById, [id]: { ...s.messagesById[id], content: (s.messagesById[id]?.content ?? "") + chunk } }
}))
```

### sendDirect primitive

```typescript
sendDirect: (content: string, historyOverride?: Message[], options?: SendOptions) => Promise<void>
```

Accepts content and history directly to avoid stale Zustand reads in retry/edit flows.

### Shiki lazy loading

```typescript
const highlighter = await import("shiki").then(m =>
  m.createHighlighter({ themes: ["github-light", "github-dark"], langs: [] })
);
```

## Test Cases

1. Normalized store: `appendToMessage` mutates only streaming message
2. `sendDirect`: retry, edit-resubmit, double-submit guard
3. `parseCitationSegments`: `[S1]`, `[Source: filename]`, no-source, duplicate citations
4. MarkdownMessage streaming caret appears/disappears with `isStreaming`
5. SourceCards: "Sources:" header, expand, view-all click
6. Composer: Enter sends, Shift+Enter newline, IME guard, stop button clickable
7. File attachment: paste/drop, upload progress, upload error, no-vault error
8. TranscriptPane virtualization: `useVirtualizer` called with correct `count` and `overscan: 5`
9. SessionRail: delete undo toast, inline rename optimistic update

## Files Changed

### New files
- `frontend/src/components/chat/MarkdownMessage.tsx`
- `frontend/src/components/chat/MessageActions.tsx`
- `frontend/src/components/chat/SourceCards.tsx`
- `frontend/src/components/chat/SourceCitation.tsx`
- `frontend/src/components/chat/Composer.tsx`

### Modified files
- `frontend/src/stores/useChatStore.ts` — normalized store
- `frontend/src/hooks/useSendMessage.ts` — sendDirect primitive, stop fix
- `frontend/src/components/chat/TranscriptPane.tsx` — layout, virtualization, no duplicate listener
- `frontend/src/components/chat/AssistantMessage.tsx` — delegates to MarkdownMessage + SourceCards
- `frontend/src/components/chat/MessageBubble.tsx` — premium user bubble
- `frontend/src/components/chat/MessageContent.tsx` — thin wrapper over MarkdownMessage
- `frontend/src/components/chat/RightPane.tsx` — heading "Evidence", tabs preserved
- `frontend/src/components/chat/SessionRail.tsx` — delete undo toast, rename polish
- `frontend/src/pages/ChatShell.tsx` — Composer integration
- `frontend/src/index.css` — typography, layout variables
- `frontend/package.json` — added shiki dependency

## Verification

All verified on branch `claude/swarm-implement-z2dH8`:

```
bun run test   → 1022 passed | 1 skipped (1023) across 42 files
bun run typecheck → clean
bun run lint      → clean
bun run build     → ✓ built in 6.90s
```
