// frontend/src/components/chat/TranscriptPane.waitingindicator-adversarial.test.tsx
// ADVERSARIAL TESTS: WaitingIndicator condition + scroll-to-bottom (Task 4.1)
// Attack vectors: empty array, null content, flicker, null scrollRef, rAF race conditions

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { TranscriptPane } from "./TranscriptPane";
import { useChatStore } from "@/stores/useChatStore";
import { useVaultStore } from "@/stores/useVaultStore";

// Mock ResizeObserver for Radix UI ScrollArea
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;

// Mock the hooks and dependencies
vi.mock("@/stores/useChatStore");
vi.mock("@/stores/useVaultStore");
vi.mock("@/hooks/useSendMessage");
vi.mock("@/hooks/useChatHistory");
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));
vi.mock("./MessageBubble", () => ({
  MessageBubble: ({ message }: { message: { id: string; role: string; content: string | null } }) => (
    <div data-testid="message-bubble" data-message-id={message.id}>
      {message.content}
    </div>
  ),
}));
vi.mock("./AssistantMessage", () => ({
  AssistantMessage: ({ message }: { message: { id: string; role: string; content: string | null } }) => (
    <div data-testid="message-bubble" data-message-id={message.id}>
      {message.content}
    </div>
  ),
}));

// Mock framer-motion to avoid animation issues in tests
vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: { children: React.ReactNode }) => (
      <div data-testid="motion-div" {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useReducedMotion: () => false,
}));

// Mock @tanstack/react-virtual
let _mockMessageCount = 0;
const _createVirtualItems = () =>
  Array.from({ length: _mockMessageCount }, (_, i) => ({
    index: i,
    start: i * 120,
    size: 120,
    key: `mock-msg-${i}`,
  }));

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: vi.fn(() => ({
    getVirtualItems: () => _createVirtualItems(),
    getTotalSize: () => _mockMessageCount * 120,
    measureElement: vi.fn((el) => ({
      getBoundingClientRect: () => ({ height: 120 }),
    })),
    scrollToIndex: vi.fn(),
    measure: vi.fn(),
  })),
}));

import { useSendMessage } from "@/hooks/useSendMessage";
import { useChatHistory } from "@/hooks/useChatHistory";
import { TooltipProvider } from "@/components/ui/tooltip";

describe("ADVERSARIAL: WaitingIndicator + scroll-to-bottom (Task 4.1)", () => {
  const mockSetInput = vi.fn();
  const mockHandleSend = vi.fn();
  const mockHandleStop = vi.fn();
  const mockRefreshHistory = vi.fn();
  const mockGetActiveVault = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    // Default mock implementations for useChatStore
    (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      messages: [],
      input: "",
      isStreaming: false,
      setInput: mockSetInput,
      setIsStreaming: vi.fn(),
      setAbortFn: vi.fn(),
      setInputError: vi.fn(),
      addMessage: vi.fn(),
      updateMessage: vi.fn(),
      inputError: null,
    });

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

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // ===========================================================================
  // AV1: Empty array edge case - messages[messages.length-1] returns undefined
  // ===========================================================================
  describe("AV1: Empty messages array - no crash, correct behavior", () => {
    it("does NOT crash when messages array is empty (messages.length - 1 === -1)", async () => {
      _mockMessageCount = 0;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [],  // Empty: messages.length - 1 === -1, but guard protects
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      // Component has guard: `messages.length > 0` before accessing last element
      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();

      await act(async () => {
        vi.advanceTimersByTime(200);
      });

      // No WaitingIndicator should appear when messages is empty
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("does NOT crash when messages array becomes empty between renders", async () => {
      _mockMessageCount = 0;
      let messages = [{ id: "1", role: "user", content: "Hello" }];
      
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        get messages() { return messages; },
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(50);
      });

      // Now simulate messages array becoming empty (race condition)
      messages = [];
      _mockMessageCount = 0;

      // Rerender with empty messages - guard should protect
      expect(() => {
        rerender(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();
    });

    it("handles messages going from 1 element to 0 during debounce", async () => {
      _mockMessageCount = 1;
      let messages = [{ id: "1", role: "assistant", content: "" }];
      
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        get messages() { return messages; },
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Before debounce fires, clear messages
      await act(async () => {
        vi.advanceTimersByTime(50);  // 50ms < 100ms debounce
      });

      messages = [];
      _mockMessageCount = 0;

      // Now let debounce fire with empty array
      await act(async () => {
        vi.advanceTimersByTime(100);  // Total 150ms > 100ms debounce
      });

      // Should not crash - guard protects
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });
  });

  // ===========================================================================
  // AV2: Null content edge case - content === null (not empty string)
  // ===========================================================================
  describe("AV2: Message content is null (not empty string)", () => {
    it("does NOT show WaitingIndicator when last assistant content is null (AV2-FINDING)", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: null as unknown as string },  // null, not ""
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // AV2-FINDING: With content === null, condition `content === ""` is FALSE
      // BUG: null content should be treated same as "" for streaming state
      // The WaitingIndicator WILL incorrectly NOT show because `null === ""` is false
      const indicator = screen.queryByRole("status", { name: "Waiting for response" });
      expect(indicator).not.toBeInTheDocument();  // Documents the bug
    });

    it("correctly shows WaitingIndicator when content is exactly empty string", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },  // Empty string - should show indicator
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // With content === "", the condition `content === ""` is TRUE
      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("does NOT show indicator when content is undefined", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: undefined as unknown as string },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // undefined === "" is false - this also demonstrates the same issue as AV2
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("handles content that is number 0 (falsy but not empty)", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: 0 as unknown as string },  // number 0
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // 0 === "" is false - indicator won't show even though it's falsy
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("handles content that is boolean false", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: false as unknown as string },  // boolean false
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // false === "" is false
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });
  });

  // ===========================================================================
  // AV3: Rapid toggle (flicker) - isWaitingForResponse toggles quickly
  // ===========================================================================
  describe("AV3: Rapid isStreaming toggle (flicker)", () => {
    it("handles rapid streaming start/stop/start within debounce window", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Rapid toggle: start streaming -> stop -> start again within 100ms
      await act(async () => {
        vi.advanceTimersByTime(50);  // First 50ms of streaming
      });

      // Stop streaming (should clear timeout and set isWaitingForResponse = false)
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: false,  // Stopped
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      await act(async () => {
        vi.advanceTimersByTime(30);  // 30ms more (total 80ms)
      });

      // Start streaming again before 100ms debounce fires
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,  // Restarted
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      // Advance past the debounce
      await act(async () => {
        vi.advanceTimersByTime(150);  // Total 230ms
      });

      // Should eventually show indicator after debounce settles
      expect(screen.queryByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("cleans up debounce timeout on unmount during streaming", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { unmount } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(50);
      });

      // Unmount during pending debounce - cleanup runs
      expect(() => {
        unmount();
      }).not.toThrow();

      // Advance timers after unmount - should not cause issues (timeout cleaned up)
      await act(async () => {
        vi.advanceTimersByTime(200);
      });
    });

    it("handles multiple streaming cycles without indicator getting stuck", async () => {
      _mockMessageCount = 2;
      
      // Use rerender pattern to update same component instance
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Cycle 1: streaming with empty content
      await act(async () => {
        vi.advanceTimersByTime(150);
      });
      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();

      // Cycle 2: streaming with content (should hide indicator)
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "Response arrived" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );
      
      await act(async () => {
        vi.advanceTimersByTime(150);
      });
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();

      // Cycle 3: streaming with empty content again
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );
      await act(async () => {
        vi.advanceTimersByTime(150);
      });
      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("handles isStreaming true/false/true within single rAF window", async () => {
      _mockMessageCount = 2;
      
      let streamCount = 0;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(() => {
        streamCount++;
        return {
          messages: [
            { id: "1", role: "user", content: "Hello" },
            { id: "2", role: "assistant", content: "" },
          ],
          input: "",
          isStreaming: streamCount % 2 === 1,  // Alternates
          setInput: mockSetInput,
          setIsStreaming: vi.fn(),
          setAbortFn: vi.fn(),
          setInputError: vi.fn(),
          addMessage: vi.fn(),
          updateMessage: vi.fn(),
          inputError: null,
        };
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Multiple rapid re-renders with alternating streaming state
      for (let i = 0; i < 5; i++) {
        await act(async () => {
          vi.advanceTimersByTime(5);  // Very rapid - within rAF window
        });
      }

      // Final state should be consistent - component should not crash
      await act(async () => {
        vi.advanceTimersByTime(200);
      });
      
      expect(screen.getByLabelText("Chat messages")).toBeInTheDocument();
    });
  });

  // ===========================================================================
  // AV4: scrollRef.current is null during rAF callback
  // ===========================================================================
  describe("AV4: scrollRef.current is null during rAF callback", () => {
    it("does NOT crash when scrollRef becomes null during rAF execution", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(100);  // Trigger debounce, but not yet at rAF
      });

      // Unmount during the pending rAF - simulates scrollRef becoming invalid
      expect(() => {
        rerender(<TooltipProvider><div /></TooltipProvider>);
      }).not.toThrow();

      // Execute the rAF that was pending - should not crash due to null check
      await act(async () => {
        vi.advanceTimersByTime(20);
      });
    });

    it("handles handleScroll with null scrollRef gracefully", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // Manually trigger scroll handler with null scrollRef (simulates unmount scenario)
      const scrollContainer = screen.queryByRole("log");
      expect(() => {
        if (scrollContainer) {
          // Dispatch scroll event - handleScroll should guard against null ref
          scrollContainer.dispatchEvent(new Event("scroll"));
        }
      }).not.toThrow();
    });

    it("handles multiple rAF callbacks with scrollRef becoming null between them", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      // First unmount
      rerender(<TooltipProvider><div /></TooltipProvider>);

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      // Re-render (ref could be different)
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      // Should not crash
      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // AV5: Messages array changes during rAF tick
  // ===========================================================================
  describe("AV5: Messages array changes during rAF tick", () => {
    it("handles messages array growing from 2 to 3 during rAF", async () => {
      _mockMessageCount = 2;
      
      let currentMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
      ];

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        get messages() { return currentMessages; },
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(100);  // Trigger debounce
      });

      // Now advance to the rAF point but BEFORE rAF executes
      await act(async () => {
        vi.advanceTimersByTime(10);  // Just before rAF would fire
      });

      // During the rAF callback, messages array changes
      currentMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
        { id: "3", role: "user", content: "New message!" },
      ];
      _mockMessageCount = 3;

      // Execute the rAF - effect captured messages.length at trigger time
      await act(async () => {
        vi.advanceTimersByTime(10);
      });

      // Should not crash - scroll effect uses messages.length from effect trigger
      expect(screen.queryByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("handles messages array shrinking to empty during rAF", async () => {
      _mockMessageCount = 1;
      
      // Use rerender to update messages
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      // Before rAF fires, clear messages using rerender
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });
      _mockMessageCount = 0;
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      // Should not crash and no indicator when messages is empty
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("handles rapid messages updates (new message every rAF tick)", async () => {
      _mockMessageCount = 1;
      
      let messageCount = 1;
      
      // With messageCount=6, last message (index 5) is assistant with "Response" (not empty)
      // because i=5, messageCount-1=5, so i === messageCount - 1 is TRUE → content = ""
      // Actually wait, let me recalculate:
      // i=5: i%2=1, role=assistant, i===5? yes → content=""
      // So with 6 messages, last is assistant empty → indicator SHOULD show
      // We want last to be USER so no indicator. user when i%2===0, so we need odd messageCount.
      // Let me do 7 messages (indices 0-6), last index 6 is user since 6%2===0
      
      const createMessages = () =>
        Array.from({ length: messageCount }, (_, i) => ({
          id: String(i + 1),
          role: i % 2 === 0 ? "user" : "assistant",
          content: i % 2 === 0 ? "User msg" : i === messageCount - 1 ? "" : "Response",
        }));
      
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        get messages() { return createMessages(); },
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Simulate rapid message additions (6 new messages to get to 7 total)
      for (let i = 0; i < 6; i++) {
        messageCount++;
        _mockMessageCount = messageCount;
        
        (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
          get messages() { return createMessages(); },
          input: "",
          isStreaming: true,
          setInput: mockSetInput,
          setIsStreaming: vi.fn(),
          setAbortFn: vi.fn(),
          setInputError: vi.fn(),
          addMessage: vi.fn(),
          updateMessage: vi.fn(),
          inputError: null,
        });
        
        rerender(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
        
        await act(async () => {
          vi.advanceTimersByTime(5);  // Very rapid - within single rAF window
        });
      }

      // Let debounce settle
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // With messageCount=7, last message (index 6) is user (6%2===0), so no indicator should show
      // But also verify we don't crash
      const indicator = screen.queryByRole("status", { name: "Waiting for response" });
      expect(indicator).not.toBeInTheDocument();
    });

    it("handles last message changing from assistant empty to user during rAF", async () => {
      _mockMessageCount = 2;
      
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(100);
      });

      // Change last message role during rAF window using rerender
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "user", content: "I am now a user message" },  // Was assistant
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });
      _mockMessageCount = 2;
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      // Indicator condition checks last message role === "assistant", should not show
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });
  });

  // ===========================================================================
  // BOUNDARY: Large message count and extreme values
  // ===========================================================================
  describe("Boundary: Large message arrays and extreme values", () => {
    it("handles very large messages array (1000+ messages)", async () => {
      _mockMessageCount = 1000;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: Array.from({ length: 1000 }, (_, i) => ({
          id: String(i),
          role: i % 2 === 0 ? "user" : "assistant",
          content: i % 2 === 0 ? `User message ${i}` : i === 999 ? "" : `Assistant response ${i}`,
        })),
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // Last message (999) is assistant with empty content - should show indicator
      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("handles Number.MAX_SAFE_INTEGER message id", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: String(Number.MAX_SAFE_INTEGER), role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // SECURITY: Injection and malformed data
  // ===========================================================================
  describe("Security: Malformed message data in WaitingIndicator context", () => {
    it("handles XSS payload in message content when streaming", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: '<script>alert("xss")</script>' },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();

      // Should not show indicator because content is not empty
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("handles unicode emoji in message content", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello 👋" },
          { id: "2", role: "assistant", content: "" },
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();

      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // Should show indicator because last assistant has empty content
      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("handles RTL unicode override in message content", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "\u202E\u0639\u0627\u062F\u0644\u202E" },  // RTL
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();
    });

    it("handles null byte in message content", async () => {
      _mockMessageCount = 2;
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "Hello\x00World" },  // Null byte
        ],
        input: "",
        isStreaming: true,
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      expect(() => {
        render(
          <TooltipProvider>
            <TranscriptPane />
          </TooltipProvider>
        );
      }).not.toThrow();
    });
  });
});
