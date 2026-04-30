# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
