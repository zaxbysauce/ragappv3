# Chat UI Bug Fixes + Conversation Forking

## Problem Statement

The chat UI had five distinct, user-reported issues that degraded the experience relative to the stated goal of matching modern AI chat UX (ChatGPT / Claude):

1. **Double thinking bubbles** — two simultaneous "Thinking •••" indicators appeared while waiting for the assistant's first response token. One was rendered inline in `AssistantMessage`, the other by a separate `WaitingIndicator` in `TranscriptPane` positioned outside the virtualizer's measured layout.

2. **Copy button silently failed** — `navigator.clipboard.writeText()` requires a secure context (HTTPS or localhost). On HTTP deployments the API is undefined; the silent `try/catch` gave no feedback. Additionally, `TranscriptPane` passed a duplicate clipboard write as the `onCopy` prop, creating two fire-and-forget calls.

3. **Auto-scroll unreliable during streaming** — three competing `useEffect` scroll hooks ran simultaneously: one via `virtualizer.scrollToIndex`, one via raw `scrollTop = scrollHeight`, and a third that called `virtualizer.measure()` on every streaming render (redundant: `@tanstack/react-virtual` v3 uses ResizeObserver automatically when `measureElement` ref is set). The 100px `isAtBottom` threshold was also too tight.

4. **Messages visually overlapped** — the `WaitingIndicator` was positioned at `top: virtualizer.getTotalSize()` inside the virtual container but was not measured by the virtualizer. The container's declared height did not include the indicator, causing scroll miscalculation and visual overlap during streaming transitions.

5. **No conversation forking** — users had no way to branch from a previous message and explore an alternate direction. No backend, store, or UI support existed.

## Goals

- Eliminate double thinking indicator
- Make copy work on both HTTP and HTTPS with visible failure feedback
- Make auto-scroll reliable and jitter-free during streaming
- Eliminate message overlap
- Implement full-stack conversation forking: branch from any message, navigate to the new fork, show fork indicator in session sidebar

## Non-Goals

- Redesigning the chat layout or visual language
- Changing streaming protocol or LLM integration
- Adding message editing in place

---

## Technical Design

### Bug Fixes

#### Double thinking / overlap (Issues 1 & 4)
- Remove `WaitingIndicator`, `isWaitingForResponse` state, `waitingDebounceRef`, `hasShownWaitingRef`, and the associated debounce + scroll `useEffect` hooks from `TranscriptPane.tsx`
- The `WaitingIndicator` rendered outside the virtualizer container, breaking layout. Its removal also resolves the overlap bug.
- In `AssistantMessage.tsx`: gate the inline "Thinking" label on `isStreaming && !message.content` (was `isStreaming` only), so it disappears once content starts flowing

#### Copy fallback (Issue 2)
- `handleCopy` in `ActionBar` tries `navigator.clipboard` first; if absent or rejects, falls back to `document.execCommand('copy')` via a hidden `<textarea>`
- On total failure: show `AlertCircle` icon + "Copy failed" tooltip for 2 s instead of silently swallowing the error
- Remove the duplicate `navigator.clipboard.writeText` call from `TranscriptPane`'s `onCopy` prop

#### Auto-scroll (Issue 3)
- Remove the `WaitingIndicator` scroll effect (gone with Issue 1 fix)
- Remove the `virtualizer.measure()` streaming effect (redundant with ResizeObserver via `measureElement` ref in v3)
- Consolidate to one auto-scroll effect: `virtualizer.scrollToIndex(messages.length - 1, { align: 'end', behavior: 'auto' })` triggered by `[messages, isAtBottom, virtualizer]`
- Increase `isAtBottom` threshold from 100 px → 150 px

### Conversation Forking (Issue 5)

#### Database
```sql
ALTER TABLE chat_sessions ADD COLUMN forked_from_session_id INTEGER;
ALTER TABLE chat_sessions ADD COLUMN fork_message_index INTEGER;
```
Migration is idempotent via `PRAGMA table_info` check.

#### API
`POST /api/chat/sessions/{session_id}/fork`
- Body: `{ "message_index": int }` (Pydantic: `ge=0`)
- Auth: requires write access to the session's vault
- Validates `message_index < len(messages)` — returns HTTP 400 on out-of-bounds
- Creates new `chat_session` with `forked_from_session_id` and `fork_message_index` set
- Copies messages `0..message_index` (inclusive) into new session
- Returns new session id, title, vault_id, and copied messages

`GET /api/chat/sessions` — updated to include `forked_from_session_id` and `fork_message_index` in session list rows.

#### Frontend
- `api.ts`: `forkChatSession(sessionId, messageIndex)` → `ForkSessionResponse`
- `ChatSession` interface gains optional `forked_from_session_id` and `fork_message_index`
- `TranscriptPane`: `handleFork(messageIndex)` — calls API, loads forked session into store, refreshes sidebar, navigates to `/chat/{newId}`; shows `toast.error()` on failure
- `AssistantMessage` / `ActionBar`: `onFork` prop; `GitBranch` button (hover-visible, same `opacity-30 group-hover:opacity-100` pattern as existing buttons)
- `MessageBubble`: `onFork` prop; `GitBranch` button with `group-hover:opacity-100`; `group` class added to wrapper
- `SessionRail`: `GitBranch` icon inline with session title when `forked_from_session_id != null`

---

## Acceptance Criteria

### AC-1: Single thinking indicator
- [ ] When a message is sent, exactly one "Thinking •••" animation appears
- [ ] The animation disappears once the first content token arrives
- [ ] The streaming cursor (pulsing block) continues while content streams

### AC-2: Copy works on HTTP and HTTPS
- [ ] Clicking copy on an assistant message copies content to clipboard on HTTPS
- [ ] Clicking copy on an assistant message copies content to clipboard on HTTP (execCommand fallback)
- [ ] When copy fails entirely, an `AlertCircle` icon appears for 2 seconds with "Copy failed" tooltip
- [ ] On success, a `Check` icon appears for 2 seconds

### AC-3: Auto-scroll reliable
- [ ] Sending a message auto-scrolls to the new response if user was within 150 px of bottom
- [ ] Streaming content auto-scrolls without jitter or position jumps
- [ ] Scrolling up mid-stream pauses auto-scroll; scrolling back to bottom resumes it

### AC-4: No message overlap
- [ ] No two message bubbles occupy the same vertical space
- [ ] Layout is stable during streaming — no position jumps as content grows

### AC-5: Conversation forking
- [ ] A "Branch from here" (`GitBranch`) button appears on hover for every message (user and assistant) when not streaming
- [ ] Clicking it creates a new session containing messages up to and including that message
- [ ] The UI navigates to the new forked session immediately
- [ ] The forked session appears in the sidebar with a `GitBranch` icon
- [ ] The original session is unchanged
- [ ] Forking from an invalid index returns a clear error (HTTP 400 backend, `toast.error` frontend)
- [ ] Fork button is hidden during active streaming

---

## Test Cases

| ID | Scenario | Expected |
|----|----------|----------|
| T-1 | Send message, observe loading state | One thinking indicator only |
| T-2 | Send message, observe transition when first token arrives | Thinking disappears, content renders, cursor continues |
| T-3 | Click copy on HTTP | Content copied via execCommand; check icon appears |
| T-4 | Click copy on HTTPS | Content copied via clipboard API; check icon appears |
| T-5 | Simulate clipboard failure | AlertCircle icon + "Copy failed" tooltip for 2 s |
| T-6 | Send long response, stay at bottom | Auto-scroll follows without jitter |
| T-7 | Scroll up mid-stream | Auto-scroll pauses |
| T-8 | Scroll back to bottom mid-stream | Auto-scroll resumes |
| T-9 | Hover over message during streaming | No fork button visible |
| T-10 | Hover over message when idle | Fork button visible |
| T-11 | Click fork on message 2 of 5 | New session with messages 0-2 created; navigate to it |
| T-12 | Forked session in sidebar | GitBranch icon visible beside session title |
| T-13 | Original session after fork | Unchanged: still has all 5 messages |
| T-14 | Fork API with out-of-bounds index | HTTP 400 returned |
| T-15 | Fork API failure → frontend | toast.error displayed |

---

## Files Changed

| File | Change type |
|------|-------------|
| `frontend/src/components/chat/TranscriptPane.tsx` | Bug fix (1, 3, 4) + fork wiring |
| `frontend/src/components/chat/AssistantMessage.tsx` | Bug fix (1, 2) + fork button |
| `frontend/src/components/chat/MessageBubble.tsx` | Fork button |
| `frontend/src/components/chat/SessionRail.tsx` | Fork indicator |
| `frontend/src/lib/api.ts` | Fork API function + ChatSession interface |
| `backend/app/models/database.py` | Fork columns migration |
| `backend/app/api/routes/chat.py` | Fork endpoint + list_sessions update |
