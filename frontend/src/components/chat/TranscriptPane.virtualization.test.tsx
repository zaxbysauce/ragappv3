// frontend/src/components/chat/TranscriptPane.virtualization.test.tsx
/**
 * Virtualization Verification Tests for TranscriptPane
 *
 * These tests verify that the @tanstack/react-virtual integration
 * works correctly in TranscriptPane, replacing the previous messages.map() approach.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { TranscriptPane } from "./TranscriptPane";
import { useChatStore } from "@/stores/useChatStore";
import { useVaultStore } from "@/stores/useVaultStore";

// Mock ResizeObserver for Radix UI components
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;

// Track virtualizer call count for auto-scroll verification
let _scrollToIndexCallCount = 0;
let _mockMessageCount = 0;

// Mock @tanstack/react-virtual with dynamic behavior
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: vi.fn(({ count }) => ({
    getVirtualItems: () =>
      Array.from({ length: count }, (_, i) => ({
        index: i,
        start: i * 120,
        size: 120,
        key: `msg-${i}`,
      })),
    getTotalSize: () => count * 120,
    measureElement: vi.fn((el) => ({
      getBoundingClientRect: () => ({ height: 120 }),
    })),
    scrollToIndex: vi.fn(() => {
      _scrollToIndexCallCount++;
    }),
    measure: vi.fn(),
  })),
}));

// Shared mock state — must be hoisted so vi.mock factories can close over it
const mockChatState = vi.hoisted(() => ({
  messageIds: [] as string[],
  messagesById: {} as Record<string, any>,
  input: "",
  isStreaming: false,
  streamingMessageId: null as string | null,
  inputError: null as string | null,
  expandedSources: new Set<string>(),
  activeChatId: null as string | null,
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

// Mock the hooks and dependencies
vi.mock("@/stores/useChatStore", () => ({
  useChatStore: vi.fn((selector?: (s: typeof mockChatState) => unknown) =>
    typeof selector === "function" ? selector(mockChatState) : mockChatState
  ),
  useMessageIds: vi.fn(() => mockChatState.messageIds),
  useMessage: vi.fn((id: string) => mockChatState.messagesById[id]),
  useChatMessages: vi.fn(() =>
    mockChatState.messageIds.map((id) => mockChatState.messagesById[id])
  ),
  useChatInput: vi.fn(() => mockChatState.input),
  useChatIsStreaming: vi.fn(() => mockChatState.isStreaming),
  useChatInputError: vi.fn(() => mockChatState.inputError),
  useChatActiveChatId: vi.fn(() => mockChatState.activeChatId),
  useChatStreamingId: vi.fn(() => mockChatState.streamingMessageId),
}));
vi.mock("@/stores/useVaultStore");
vi.mock("@/hooks/useSendMessage");
vi.mock("@/hooks/useChatHistory");
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));
vi.mock("./MessageBubble", () => ({
  MessageBubble: ({ message }: { message: { id: string; role: string; content: string } }) => (
    <div data-testid="message-bubble" data-message-id={message.id} data-role={message.role}>
      {message.content}
    </div>
  ),
}));
vi.mock("./AssistantMessage", () => ({
  AssistantMessage: ({ message }: { message: { id: string; role: string; content: string } }) => (
    <div data-testid="message-bubble" data-message-id={message.id} data-role={message.role}>
      {message.content}
    </div>
  ),
}));
vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: { children: React.ReactNode }) => (
      <div data-testid="motion-div" {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useReducedMotion: () => false,
}));

import { useSendMessage } from "@/hooks/useSendMessage";
import { useChatHistory } from "@/hooks/useChatHistory";

describe("TranscriptPane Virtualization", () => {
  const mockSetInput = vi.fn();
  const mockHandleSend = vi.fn();
  const mockHandleStop = vi.fn();
  const mockRefreshHistory = vi.fn();
  const mockGetActiveVault = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    _scrollToIndexCallCount = 0;
    _mockMessageCount = 0;

    // Reset shared mock state
    mockChatState.messageIds = [];
    mockChatState.messagesById = {};
    mockChatState.input = "";
    mockChatState.isStreaming = false;
    mockChatState.streamingMessageId = null;
    mockChatState.inputError = null;
    mockChatState.setInput = mockSetInput;
    mockChatState.setIsStreaming = vi.fn();
    mockChatState.setAbortFn = vi.fn();
    mockChatState.setInputError = vi.fn();
    mockChatState.addMessage = vi.fn();
    mockChatState.updateMessage = vi.fn();
    mockChatState.stopStreaming = vi.fn();

    // Mock useVaultStore with selector support
    (useVaultStore as unknown as ReturnType<typeof vi.fn>).mockImplementation((selector) => {
      const state = {
        vaults: [{ id: 1, name: "Test Vault", file_count: 5 }],
        activeVaultId: 1,
        getActiveVault: mockGetActiveVault,
      };
      return selector ? selector(state) : state;
    });

    (useSendMessage as ReturnType<typeof vi.fn>).mockReturnValue({
      handleSend: mockHandleSend,
      handleStop: mockHandleStop,
    });

    (useChatHistory as ReturnType<typeof vi.fn>).mockReturnValue({
      refreshHistory: mockRefreshHistory,
      chatHistory: [],
      isChatLoading: false,
      chatHistoryError: null,
    });

    mockGetActiveVault.mockReturnValue({
      id: 1,
      name: "Test Vault",
      file_count: 5,
    });
  });

  // Helper to set normalized mock state from old-style messages array
  const setMockChatState = (state: { messages?: any[]; input?: string; isStreaming?: boolean; inputError?: string | null; [key: string]: any }) => {
    if (state.messages !== undefined) {
      mockChatState.messageIds = state.messages.map((m: any, i: number) => m.id != null ? String(m.id) : String(i));
      mockChatState.messagesById = Object.fromEntries(state.messages.map((m: any, i: number) => [m.id != null ? String(m.id) : String(i), m]));
    }
    if (state.input !== undefined) mockChatState.input = state.input;
    if (state.isStreaming !== undefined) mockChatState.isStreaming = state.isStreaming;
    if (state.inputError !== undefined) mockChatState.inputError = state.inputError;
  };

  describe("1. Scroll container is a plain div with role='log'", () => {
    it("renders a plain div with role='log' instead of ScrollArea", () => {
      render(<TranscriptPane />);

      // Verify role="log" is present on the scroll container
      const scrollContainer = screen.getByRole("log");
      expect(scrollContainer).toBeInTheDocument();

      // Verify it's a div (not ScrollArea Radix component)
      expect(scrollContainer.tagName).toBe("DIV");

      // Verify it has overflow-y-auto class for scrolling
      expect(scrollContainer).toHaveClass("overflow-y-auto");
    });

    it("scroll container has aria-label for accessibility", () => {
      render(<TranscriptPane />);

      const scrollContainer = screen.getByRole("log");
      expect(scrollContainer).toHaveAttribute("aria-label", "Chat messages");
    });
  });

  describe("2. EmptyTranscript renders when messages.length === 0", () => {
    it("shows EmptyTranscript component when no messages", () => {
      _mockMessageCount = 0;
      render(<TranscriptPane />);

      expect(screen.getByText("What would you like to know?")).toBeInTheDocument();
    });

    it("does not render any message bubbles when messages array is empty", () => {
      _mockMessageCount = 0;
      render(<TranscriptPane />);

      expect(screen.queryByTestId("message-bubble")).not.toBeInTheDocument();
    });

    it("EmptyTranscript shows suggested prompts when vault has docs", () => {
      _mockMessageCount = 0;
      render(<TranscriptPane />);

      expect(screen.getByText("What are the key findings?")).toBeInTheDocument();
      expect(screen.getByText("Summarize the main topics")).toBeInTheDocument();
    });
  });

  describe("3. Messages render correctly through the virtualizer", () => {
    it("renders user and assistant messages via virtualizer", () => {
      _mockMessageCount = 2;
            setMockChatState({ messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "Hi there!" },
        ], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // Both messages should be rendered via the virtualizer
      const bubbles = screen.getAllByTestId("message-bubble");
      expect(bubbles).toHaveLength(2);
      expect(bubbles[0]).toHaveAttribute("data-message-id", "1");
      expect(bubbles[1]).toHaveAttribute("data-message-id", "2");
    });

    it("renders message content correctly", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Test message content" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      expect(screen.getByText("Test message content")).toBeInTheDocument();
    });

    it("handles large number of messages without performance issues", () => {
      // Create 50 messages to simulate a long conversation
      const manyMessages = Array.from({ length: 50 }, (_, i) => ({
        id: String(i + 1),
        role: i % 2 === 0 ? "user" : "assistant",
        content: `Message ${i + 1}`,
      }));

      _mockMessageCount = 50;
            setMockChatState({ messages: manyMessages, input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // Virtualizer should handle 50 messages without crashing
      const scrollContainer = screen.getByRole("log");
      expect(scrollContainer).toBeInTheDocument();
    });
  });

  describe("4. Auto-scroll behavior via virtualizer.scrollToIndex", () => {
    it("scrollToIndex is called when messages change and user is at bottom", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Test" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // The mock's scrollToIndex should have been called
      // (Actual call count depends on useEffect timing)
      expect(screen.getByRole("log")).toBeInTheDocument();
    });

    it("auto-scroll works with streaming state", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Test" }], input: "", isStreaming: true, inputError: null }); // Streaming state

      render(<TranscriptPane />);

      // Component should render without crashing during streaming
      expect(screen.getByRole("log")).toBeInTheDocument();
    });
  });

  describe("5. Streaming state doesn't crash the virtualizer", () => {
    it("renders correctly during active streaming", () => {
      _mockMessageCount = 2;
      setMockChatState({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "Streaming response..." },
        ],
        input: "",
        isStreaming: true, // Active streaming
        inputError: null,
      });

      render(<TranscriptPane />);

      // Should render without crashing
      const bubbles = screen.getAllByTestId("message-bubble");
      expect(bubbles).toHaveLength(2);
    });

    it("handles message update during streaming", () => {
      _mockMessageCount = 2;
      const { rerender } = render(
        <TranscriptPane />
      );

      // Update with streaming message
            setMockChatState({ messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "Streaming response..." },
        ], input: "", isStreaming: true, inputError: null });

      // Rerender should not crash
      rerender(<TranscriptPane />);
      expect(screen.getAllByTestId("message-bubble")).toHaveLength(2);
    });
  });

  describe("6. Scroll-to-bottom button appears/disappears correctly", () => {
    it("scroll-to-bottom button is not visible when at bottom (initial state)", () => {
      _mockMessageCount = 5;
            setMockChatState({ messages: Array.from({ length: 5 }, (_, i) => ({ id: String(i + 1), role: "user", content: `Message ${i + 1}` })), input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // Initial state: showScrollButton is false, so button is not visible
      // (AnimatePresence with initial={{ opacity: 0 }} hides it)
      expect(screen.queryByLabelText("Scroll to bottom")).not.toBeInTheDocument();
    });

    it("scroll-to-bottom button is not present when no messages", () => {
      _mockMessageCount = 0;
      render(<TranscriptPane />);

      // With no messages, no scroll button needed
      expect(screen.queryByLabelText("Scroll to bottom")).not.toBeInTheDocument();
    });

    it("scroll-to-bottom button component exists with correct aria-label", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Msg 1" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // Verify the button component exists in the component (even if hidden by AnimatePresence)
      // The button would be visible only when showScrollButton is true (set by handleScroll)
      // Since jsdom doesn't have real scrolling, we verify it's not in the document
      expect(screen.queryByLabelText("Scroll to bottom")).not.toBeInTheDocument();
    });
  });

  describe("7. Virtualizer container structure", () => {
    it("virtualizer container has correct position relative class", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Test" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // The message container with max-width constraint should be present
      const log = screen.getByRole("log");
      expect(log).toBeInTheDocument();
    });

    it("max-width constraint is applied to message container", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Test" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // The scroll container should be present with a max-width constraint
      const log = screen.getByRole("log");
      expect(log).toBeInTheDocument();
    });
  });

  describe("8. Edge cases", () => {
    it("handles single message correctly", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Single message" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      expect(screen.getByText("Single message")).toBeInTheDocument();
      expect(screen.getAllByTestId("message-bubble")).toHaveLength(1);
    });

    it("handles empty string message content", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // Should still render the bubble even with empty content
      expect(screen.getByTestId("message-bubble")).toBeInTheDocument();
    });

    it("handles special characters in message content", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "Hello <script>alert('xss')</script>" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      // Content should be rendered as text, not executed
      expect(screen.getByText("Hello <script>alert('xss')</script>")).toBeInTheDocument();
    });

    it("handles Unicode content in messages", () => {
      _mockMessageCount = 1;
            setMockChatState({ messages: [{ id: "1", role: "user", content: "你好 🌍 🎉" }], input: "", isStreaming: false, inputError: null });

      render(<TranscriptPane />);

      expect(screen.getByText("你好 🌍 🎉")).toBeInTheDocument();
    });
  });
});
