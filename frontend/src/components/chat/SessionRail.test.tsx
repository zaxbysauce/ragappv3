// frontend/src/components/chat/SessionRail.test.tsx
// Keyboard navigation tests for SessionRail roving tabindex (WCAG 2.4.3)

import { render, screen, fireEvent, act } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";
import { SessionGroup, SessionItem } from "./SessionRail";
import type { ChatSession } from "@/lib/api";

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeSession(id: number, title = "Test Session"): ChatSession {
  return {
    id,
    title,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    vault_id: 1,
    message_count: 0,
  };
}

function makeDefaultSessionProps(
  index: number,
  overrides: Partial<import("./SessionRail").SessionItemProps> = {}
): import("./SessionRail").SessionItemProps {
  const session = makeSession(index + 1);
  return {
    session,
    isActive: false,
    isPinned: false,
    onClick: vi.fn(),
    onRename: vi.fn(),
    onPinToggle: vi.fn(),
    onDelete: vi.fn(),
    tabIndex: -1,
    onKeyDown: vi.fn(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// SessionItem keyboard activation (Enter / Space)
// ---------------------------------------------------------------------------

describe("SessionItem keyboard activation", () => {
  test("Enter key calls onClick", () => {
    const onClick = vi.fn();
    const onKeyDown = vi.fn();
    const props = makeDefaultSessionProps(0, { onClick, onKeyDown });
    render(<SessionItem {...props} />);

    // Target the outer SessionItem div by its aria-label (not nested action buttons)
    const item = screen.getByLabelText("Chat session: Test Session");
    fireEvent.keyDown(item, { key: "Enter", bubbles: true });

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  test("Space key calls onClick", () => {
    const onClick = vi.fn();
    const onKeyDown = vi.fn();
    const props = makeDefaultSessionProps(0, { onClick, onKeyDown });
    render(<SessionItem {...props} />);

    const item = screen.getByLabelText("Chat session: Test Session");
    fireEvent.keyDown(item, { key: " ", bubbles: true });

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  test("ArrowUp key does NOT call onClick (navigation handled by parent)", () => {
    const onClick = vi.fn();
    const onKeyDown = vi.fn();
    const props = makeDefaultSessionProps(0, { onClick, onKeyDown });
    render(<SessionItem {...props} />);

    const item = screen.getByLabelText("Chat session: Test Session");
    fireEvent.keyDown(item, { key: "ArrowUp", bubbles: true });

    expect(onClick).not.toHaveBeenCalled();
  });

  test("ArrowDown key does NOT call onClick (navigation handled by parent)", () => {
    const onClick = vi.fn();
    const onKeyDown = vi.fn();
    const props = makeDefaultSessionProps(0, { onClick, onKeyDown });
    render(<SessionItem {...props} />);

    const item = screen.getByLabelText("Chat session: Test Session");
    fireEvent.keyDown(item, { key: "ArrowDown", bubbles: true });

    expect(onClick).not.toHaveBeenCalled();
  });

  test("clicking item calls onClick", () => {
    const onClick = vi.fn();
    const props = makeDefaultSessionProps(0, { onClick });
    render(<SessionItem {...props} />);

    // Target outer div via aria-label to avoid nested action buttons
    fireEvent.click(screen.getByLabelText("Chat session: Test Session"));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// SessionGroup roving tabindex keyboard navigation
// ---------------------------------------------------------------------------

describe("SessionGroup roving tabindex", () => {
  let sessions: ChatSession[];
  let onFocusedIndexChange: ReturnType<typeof vi.fn>;
  let onSessionClick: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessions = [makeSession(1, "Session One"), makeSession(2, "Session Two"), makeSession(3, "Session Three")];
    onFocusedIndexChange = vi.fn();
    onSessionClick = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Test 1: ArrowDown moves focus to next item
  // -------------------------------------------------------------------------
  test("ArrowDown moves focus to next item", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "ArrowDown" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(1);
  });

  // -------------------------------------------------------------------------
  // Test 2: ArrowUp moves focus to previous item
  // -------------------------------------------------------------------------
  test("ArrowUp moves focus to previous item", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={1}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "ArrowUp" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(0);
  });

  // -------------------------------------------------------------------------
  // Test 3: ArrowDown at end stays at last item
  // -------------------------------------------------------------------------
  test("ArrowDown at end stays at last item", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={2} // last item (index 2 of 3)
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "ArrowDown" });

    // Should call with clamped value (last index), not beyond
    expect(onFocusedIndexChange).toHaveBeenCalledWith(2);
  });

  // -------------------------------------------------------------------------
  // Test 4: ArrowUp at start stays at first item
  // -------------------------------------------------------------------------
  test("ArrowUp at start stays at first item", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0} // first item
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "ArrowUp" });

    // Should call with clamped value (0), not negative
    expect(onFocusedIndexChange).toHaveBeenCalledWith(0);
  });

  // -------------------------------------------------------------------------
  // Test 5: Home key moves to first item
  // -------------------------------------------------------------------------
  test("Home key moves to first item", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={2} // currently at last
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "Home" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(0);
  });

  // -------------------------------------------------------------------------
  // Test 6: End key moves to last item
  // -------------------------------------------------------------------------
  test("End key moves to last item", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0} // currently at first
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "End" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(2);
  });

  // -------------------------------------------------------------------------
  // Test 7: Click updates focusedIndex
  // -------------------------------------------------------------------------
  test("clicking a session item updates focusedIndex", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    // Click the second session item (index 1) — use aria-label to avoid nested action buttons
    const items = screen.getAllByLabelText(/^Chat session:/);
    fireEvent.click(items[1]);

    expect(onFocusedIndexChange).toHaveBeenCalledWith(1);
  });

  // -------------------------------------------------------------------------
  // Test 8: Tab key does NOT call onFocusedIndexChange (exits list)
  // -------------------------------------------------------------------------
  test("Tab key does not trigger onFocusedIndexChange", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "Tab" });

    // Tab is NOT handled — the handler does not have a Tab branch
    expect(onFocusedIndexChange).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Additional: Arrow keys with single-item list
  // -------------------------------------------------------------------------
  test("ArrowDown with single item calls onFocusedIndexChange with 0 (no-op)", () => {
    const singleSession = [makeSession(99, "Only Session")];
    render(
      <SessionGroup
        label="Today"
        sessions={singleSession}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "ArrowDown" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(0);
  });

  test("ArrowUp with single item calls onFocusedIndexChange with 0 (no-op)", () => {
    const singleSession = [makeSession(99, "Only Session")];
    render(
      <SessionGroup
        label="Today"
        sessions={singleSession}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "ArrowUp" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(0);
  });

  // -------------------------------------------------------------------------
  // Additional: Empty sessions list — no keyboard navigation
  // -------------------------------------------------------------------------
  test("empty sessions list does not call onFocusedIndexChange on arrow keys", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={[]}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    // Empty groups render nothing — no list to dispatch events on
    expect(screen.queryByRole("list")).toBeNull();
    expect(onFocusedIndexChange).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Additional: tabIndex reflects roving tabindex pattern
  // -------------------------------------------------------------------------
  test("focused item has tabIndex=0, others have tabIndex=-1", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={1} // second item focused
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const items = screen.getAllByLabelText(/^Chat session:/);
    expect(items[0]).toHaveAttribute("tabIndex", "-1");
    expect(items[1]).toHaveAttribute("tabIndex", "0");
    expect(items[2]).toHaveAttribute("tabIndex", "-1");
  });

  // -------------------------------------------------------------------------
  // Additional: Home when already at first — still calls with 0
  // -------------------------------------------------------------------------
  test("Home when already at first item calls onFocusedIndexChange with 0", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={0}
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "Home" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(0);
  });

  // -------------------------------------------------------------------------
  // Additional: End when already at last — still calls with last index
  // -------------------------------------------------------------------------
  test("End when already at last item calls onFocusedIndexChange with last index", () => {
    render(
      <SessionGroup
        label="Today"
        sessions={sessions}
        activeSessionId={null}
        onSessionClick={onSessionClick}
        onSessionRename={vi.fn()}
        onSessionPinToggle={vi.fn()}
        onSessionDelete={vi.fn()}
        isSessionPinned={() => false}
        focusedIndex={2} // last
        onFocusedIndexChange={onFocusedIndexChange}
        indexOffset={0}
      />
    );

    const list = screen.getByRole("list");
    fireEvent.keyDown(list, { key: "End" });

    expect(onFocusedIndexChange).toHaveBeenCalledWith(2);
  });
});
