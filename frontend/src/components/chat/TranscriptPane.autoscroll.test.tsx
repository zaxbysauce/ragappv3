/**
 * Tests for the streaming auto-scroll behavior added in P1.1.
 *
 * Specifically:
 * - Token growth (streamingContentLength increasing without messageIds.length
 *   changing) triggers auto-scroll while pinned to bottom.
 * - Once the user scrolls up, auto-scroll stops even if content keeps growing.
 * - Clicking "New messages" repins to bottom and re-enables auto-scroll.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, act } from "@testing-library/react";
import { TranscriptPane } from "./TranscriptPane";

// Hoisted shared mock state — vi.mock factories close over it.
const mockState = vi.hoisted(() => ({
  messageIds: ["m1", "m2"] as string[],
  messagesById: {
    m1: { id: "m1", role: "user", content: "hi" },
    m2: { id: "m2", role: "assistant", content: "" },
  } as Record<string, any>,
  input: "",
  isStreaming: true,
  streamingMessageId: "m2" as string | null,
  inputError: null,
  expandedSources: new Set<string>(),
  activeChatId: null,
  abortFn: null,
  setInput: vi.fn(),
  setIsStreaming: vi.fn(),
  setAbortFn: vi.fn(),
  setInputError: vi.fn(),
  addMessage: vi.fn(),
  updateMessage: vi.fn(),
  appendToMessage: vi.fn(),
  removeMessagesFrom: vi.fn(),
  stopStreaming: vi.fn(),
  loadChat: vi.fn(),
  newChat: vi.fn(),
}));

// Capture every scrollToIndex call so the test can assert how many auto-scroll
// triggers fired across token growth.
const scrollToIndexMock = vi.fn();
const measureMock = vi.fn();

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: () => ({
    scrollToIndex: scrollToIndexMock,
    measure: measureMock,
    getVirtualItems: () => [],
    getTotalSize: () => 1000,
    measureElement: () => 0,
  }),
}));

vi.mock("@/stores/useChatStore", () => ({
  useChatStore: vi.fn((selector?: (s: typeof mockState) => unknown) =>
    typeof selector === "function" ? selector(mockState) : mockState
  ),
  useMessageIds: vi.fn(() => mockState.messageIds),
  useMessage: vi.fn((id: string) => mockState.messagesById[id]),
  useChatMessages: vi.fn(() =>
    mockState.messageIds.map((id) => mockState.messagesById[id])
  ),
  useChatInput: vi.fn(() => mockState.input),
  useChatIsStreaming: vi.fn(() => mockState.isStreaming),
  useChatInputError: vi.fn(() => mockState.inputError),
  useChatActiveChatId: vi.fn(() => mockState.activeChatId),
  useChatStreamingId: vi.fn(() => mockState.streamingMessageId),
  useStreamingMessageContentLength: vi.fn(() => {
    const id = mockState.streamingMessageId;
    if (!id) return 0;
    return (mockState.messagesById[id]?.content ?? "").length;
  }),
}));

vi.mock("@/stores/useVaultStore", () => ({
  useVaultStore: Object.assign(
    vi.fn((selector?: (s: any) => unknown) => {
      const state = {
        activeVaultId: 1,
        getActiveVault: () => ({ id: 1, name: "v", file_count: 1 }),
      };
      return typeof selector === "function" ? selector(state) : state;
    }),
    {
      getState: () => ({ activeVaultId: 1 }),
    }
  ),
}));

vi.mock("@/stores/useAuthStore", () => ({
  useAuthStore: vi.fn((selector?: (s: any) => unknown) => {
    const state = { user: null };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

vi.mock("@/stores/useChatShellStore", () => ({
  useChatShellStore: vi.fn((selector?: (s: any) => unknown) => {
    const state = {
      activeSessionId: null,
      activeSessionTitle: null,
      openRightPane: vi.fn(),
      closeRightPane: vi.fn(),
      setActiveRightTab: vi.fn(),
      activeRightTab: "evidence",
      selectedEvidenceSource: null,
      setSelectedEvidenceSource: vi.fn(),
    };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

vi.mock("@/hooks/useSendMessage", () => ({
  useSendMessage: () => ({
    handleSend: vi.fn(),
    handleStop: vi.fn(),
    handleKeyDown: vi.fn(),
    handleInputChange: vi.fn(),
    sendDirect: vi.fn(),
  }),
}));

vi.mock("@/hooks/useChatHistory", () => ({
  useChatHistory: () => ({ refreshHistory: vi.fn() }),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("./MessageBubble", () => ({
  MessageBubble: () => <div data-testid="bubble" />,
}));

vi.mock("./AssistantMessage", () => ({
  AssistantMessage: () => <div data-testid="assistant-msg" />,
}));

vi.mock("./WaitingIndicator", () => ({
  WaitingIndicator: () => <div data-testid="waiting" />,
}));

vi.mock("./Composer", () => ({
  Composer: () => <div data-testid="composer" />,
}));

beforeEach(() => {
  scrollToIndexMock.mockReset();
  measureMock.mockReset();
  mockState.messageIds = ["m1", "m2"];
  mockState.messagesById = {
    m1: { id: "m1", role: "user", content: "hi" },
    m2: { id: "m2", role: "assistant", content: "" },
  };
  mockState.streamingMessageId = "m2";
  mockState.isStreaming = true;
  // Stub rAF to invoke synchronously so scroll effects flush in tests.
  vi.spyOn(global, "requestAnimationFrame").mockImplementation((cb: any) => {
    cb(0);
    return 0 as unknown as number;
  });
});

function renderAndGetScrollEl() {
  const result = render(<TranscriptPane />);
  // The transcript scroll container has aria-label="Chat messages".
  const scrollEl = result.container.querySelector(
    '[aria-label="Chat messages"]'
  ) as HTMLDivElement;
  // Stub layout so handleScroll's distance math is deterministic.
  Object.defineProperty(scrollEl, "scrollHeight", {
    configurable: true,
    value: 1000,
  });
  Object.defineProperty(scrollEl, "clientHeight", {
    configurable: true,
    value: 500,
  });
  // Initially scrolled to bottom.
  scrollEl.scrollTop = 500;
  return { result, scrollEl };
}

describe("TranscriptPane streaming auto-scroll", () => {
  it("scrolls when streaming content length grows while pinned at bottom", () => {
    const { rerender } = render(<TranscriptPane />);
    // Initial render → at-bottom by default.
    const initialCalls = scrollToIndexMock.mock.calls.length;

    // Simulate token growth: content of m2 grows.
    act(() => {
      mockState.messagesById = {
        ...mockState.messagesById,
        m2: { ...mockState.messagesById.m2, content: "Hello, " },
      };
      rerender(<TranscriptPane />);
    });

    expect(scrollToIndexMock.mock.calls.length).toBeGreaterThan(initialCalls);
    // The most recent call must target the last index with align: "end".
    const last =
      scrollToIndexMock.mock.calls[scrollToIndexMock.mock.calls.length - 1];
    expect(last[0]).toBe(1); // last index of [m1, m2]
    expect(last[1]).toMatchObject({ align: "end" });
  });

  it("stops auto-scrolling once the user scrolls up", () => {
    const { result, scrollEl } = renderAndGetScrollEl();

    // First: simulate the user scrolling up.
    Object.defineProperty(scrollEl, "scrollTop", {
      configurable: true,
      writable: true,
      value: 0,
    });
    act(() => {
      fireEvent.scroll(scrollEl);
    });
    const callsAfterScrollUp = scrollToIndexMock.mock.calls.length;

    // Now grow streaming content. Auto-scroll must NOT fire.
    act(() => {
      mockState.messagesById = {
        ...mockState.messagesById,
        m2: { ...mockState.messagesById.m2, content: "growing tokens..." },
      };
      result.rerender(<TranscriptPane />);
    });

    expect(scrollToIndexMock.mock.calls.length).toBe(callsAfterScrollUp);
  });

  it("does not auto-scroll on token growth when no message is streaming", () => {
    mockState.streamingMessageId = null;
    mockState.isStreaming = false;
    mockState.messagesById = {
      m1: { id: "m1", role: "user", content: "hi" },
      m2: { id: "m2", role: "assistant", content: "" },
    };
    const { rerender } = render(<TranscriptPane />);
    const initialCalls = scrollToIndexMock.mock.calls.length;

    // Growing content of m2 outside a streaming session — selector returns 0,
    // so the token-growth effect shouldn't fire.
    act(() => {
      mockState.messagesById = {
        ...mockState.messagesById,
        m2: { ...mockState.messagesById.m2, content: "later edit" },
      };
      rerender(<TranscriptPane />);
    });

    // scrollToIndex may have fired once for the initial-render new-message
    // effect, but not again from the streaming-length effect (streamingId=null
    // → selector returns 0 → effect early-returns).
    expect(scrollToIndexMock.mock.calls.length).toBe(initialCalls);
  });
});
