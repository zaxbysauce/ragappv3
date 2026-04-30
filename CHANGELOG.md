# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.3] - 2026-04-30

### Added
- Message feedback (thumbs up/down) persisted to database via new `PATCH /chat/sessions/{session_id}/messages/{message_id}/feedback` route; feedback round-trips through GET session response and initializes from server state
- DB migration (`migrate_add_feedback_column`) adds `feedback TEXT` column to `chat_messages` with idempotency guard
- Session rail drag-to-resize: drag handle on right edge of sidebar adjusts width (200–400 px, stored in `useChatShellStore`); `sessionRailWidth` / `setSessionRailWidth` added to shell store
- Message timestamp shown on hover (desktop) / always (touch): `<time>` element with `formatRelativeTime` in `MessageBubble`
- Edit button (pencil icon) on user messages in `MessageBubble`; clicking populates the composer and trims forward messages
- "Try again →" button inside error boxes wired to `onRetry` callback
- TanStack Virtual scrolling in `SessionRail` with JSDOM fallback for tests; `MemoryPage` similarly virtualized
- `WaitingIndicator` rendered at `TranscriptPane` row level when streaming with empty content (replaces inline bounce dots)
- Evidence jump-to-answer: custom `evidence:jump-to-answer` window event scrolls TranscriptPane to the cited message and flashes a highlight ring
- `formatRelativeTime` extracted to `frontend/src/lib/formatters.ts` as a shared utility
- EmptyState components replace freeform empty-state markup in `RightPane` and `VaultsPage`
- Skeleton cards replace Loader2 spinner on `VaultsPage` loading state
- Accessible Labels (`<Label htmlFor>`) added to vault name/description inputs in `VaultsPage`

### Changed
- Copy button (`ActionBar`) strips `[Source:…]` and `[S\d+]` citation markers before writing to clipboard; `CopyButton` (code blocks) gains execCommand fallback and `toast.error` on failure
- Session rail toggle button no longer hidden on desktop (`md:hidden` removed); sidebar can be opened/closed on all screen sizes
- Active session in rail: `bg-accent/50` replaced with `bg-primary/10 border-l-2 border-primary` left-accent style
- `MessageBubble` accepts `userInitial` as prop (computed once in `TranscriptPane`) instead of subscribing to `useAuthStore` per row
- `renderedContent` in `AssistantMessage` wrapped in `useMemo` to avoid re-parsing on every streaming token
- Auto-scroll dependency narrowed to `messages.length` (not full array reference) to reduce spurious re-renders
- Fork button and edit button always visible on touch devices (`[@media(pointer:coarse)]:opacity-100`)
- Debug panel and debug button gated behind `import.meta.env.DEV`
- `DocumentsPage` table rows get correct ARIA roles (`role="row"` / `role="rowgroup"`)
- Amber warning banner in `DocumentsPage` gains `dark:text-amber-300` for dark-mode contrast
- `SessionRail` error state uses `AlertCircle` icon with a Retry button
- `RightPane` source text truncation delegated to CSS `line-clamp-2` / `truncate` (removes JS `.slice()`)
- `useSendMessage` maps DB message IDs back via `migrateId`, migrating localStorage feedback keys and updating message state

### Fixed
- Feedback API call correctly validates vault-level authorization via `evaluate_policy` before updating (prevents cross-user writes)
- `ChatHistory.tsx` deleted (was dead code with no importers)
- `SessionRail` no longer clears the fetched-IDs cache on empty search query (prevents flash re-fetch)

## [1.0.2] - 2026-04-30

### Added
- File-type icon utility (`frontend/src/lib/fileIcon.tsx`) with color-coded Lucide icons for PDF (red), DOCX (blue), Markdown (teal), spreadsheets (green), and generic fallback
- File-type icons integrated into SourcesPanel, DocumentCard, and DocumentsPage table rows
- Citation chip source-snippet tooltips — hovering a `[Source: …]` chip now shows up to 100 chars of the matched passage
- Code block rendering in assistant messages: language badge, copy-to-clipboard button, proper `pre`/`code` wrapping via ReactMarkdown component overrides
- Suggested-prompt chips enriched with contextual Lucide icons (TrendingUp, AlignLeft, Database, CheckCircle2)

### Changed
- ActionBar default opacity raised from 30% to 60% for better discoverability; always 100% on touch/coarse-pointer devices (`[@media(pointer:coarse)]`)
- Mobile bottom-nav labels bumped from 10 px to `text-xs` (12 px) to meet WCAG minimum font-size
- User message rows: left-border accent (`border-l-2 border-primary/40`) + slightly stronger background (`bg-primary/[0.12]`) replacing flat `bg-primary/10`
- User avatar now renders the authenticated user's initials (from `useAuthStore`) instead of a static `<User>` icon
- Composer textarea border highlights on `focus-within` for clearer focus state
- Send and Stop buttons bumped from `size="sm"` to `size="default"` for larger tap targets
- SourcesPanel scroll area set to `h-full` so it fills its container rather than a fixed 400 px height
- Removed duplicate "View all sources" text link that competed with the existing "+N more" chip button
- NavigationRail active-indicator motion pill removed (caused layout shift); logo wrapper simplified

### Fixed
- `fileIcon.tsx` handles `null`/`undefined` filenames without crashing (null-coalescing before `.split`)
- AssistantMessage tests updated to match the count-prefixed aria-label `"View all N sources"` and the new `opacity-60` class
