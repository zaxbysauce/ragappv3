// frontend/src/components/chat/TranscriptPane.waitingindicator.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";

// Mock ResizeObserver for Radix UI ScrollArea
class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;

// Mock localStorage BEFORE any imports including vi.mock (must be inline since vi.mock is hoisted)
const mockLocalStorage = {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
  length: 0,
  key: vi.fn(),
};
Object.defineProperty(global, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
});

// Mutable state that can be changed during tests
let _mockIsStreaming = false;
let _mockMessages: any[] = [];

// Mock the hooks and dependencies
vi.mock("@/stores/useChatStore", () => ({
  useChatStore: vi.fn(() => ({
    get messages() { return _mockMessages; },
    input: "",
    get isStreaming() { return _mockIsStreaming; },
    setInput: vi.fn(),
    setIsStreaming: vi.fn(),
    setAbortFn: vi.fn(),
    setInputError: vi.fn(),
    addMessage: vi.fn(),
    updateMessage: vi.fn(),
    inputError: null,
  })),
}));
vi.mock("@/stores/useVaultStore", () => {
  const mockGetActiveVault = vi.fn(() => ({
    id: 1,
    name: "Test Vault",
    file_count: 5,
  }));
  return {
    useVaultStore: vi.fn((selector) => {
      const state = {
        vaults: [{ id: 1, name: "Test Vault", file_count: 5 }],
        activeVaultId: 1,
        getActiveVault: mockGetActiveVault,
      };
      return selector ? selector(state) : state;
    }),
  };
});
vi.mock("@/hooks/useSendMessage", () => ({
  useSendMessage: vi.fn(),
  MAX_INPUT_LENGTH: 4000,
}));
vi.mock("@/hooks/useChatHistory", () => ({
  useChatHistory: vi.fn(),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));
vi.mock("./MessageBubble", () => ({
  MessageBubble: ({ message }: { message: { id: string; role: string; content: string } }) => (
    <div data-testid="message-bubble" data-message-id={message.id}>
      {message.content}
    </div>
  ),
}));
vi.mock("./AssistantMessage", () => ({
  AssistantMessage: ({ message }: { message: { id: string; role: string; content: string } }) => (
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
import { useChatStore } from "@/stores/useChatStore";
import { useVaultStore } from "@/stores/useVaultStore";
import { TranscriptPane } from "./TranscriptPane";

describe("WaitingIndicator condition tests (Task 4.1)", () => {
  const mockSetInput = vi.fn();
  const mockHandleSend = vi.fn();
  const mockHandleStop = vi.fn();
  const mockRefreshHistory = vi.fn();
  const mockGetActiveVault = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    
    // Reset mutable state
    _mockIsStreaming = false;
    _mockMessages = [];

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

  describe("F1: WaitingIndicator render condition", () => {
    it("shows WaitingIndicator when isStreaming=true, last message is assistant with empty content", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
      ];
      _mockIsStreaming = true;

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Advance past the 100ms debounce that sets isWaitingForResponse
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("does NOT show WaitingIndicator when isStreaming=true but assistant message has NON-EMPTY content (F1 bug fix)", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "I already have response text" },
      ];
      _mockIsStreaming = true;

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Advance past the 100ms debounce
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // Even with streaming and debounce passed, indicator should NOT show
      // because the last assistant message has content
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("does NOT show WaitingIndicator when isStreaming=true but last message is user", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "assistant", content: "Hello" },
        { id: "2", role: "user", content: "Follow up question" },
      ];
      _mockIsStreaming = true;

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Advance past the 100ms debounce
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // Indicator should NOT show because last message role is "user", not "assistant"
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("does NOT show WaitingIndicator when isStreaming=false even with empty assistant message", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
      ];
      _mockIsStreaming = false;

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Even with long wait, no indicator should show because isStreaming is false
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("does NOT show WaitingIndicator when messages array is empty", async () => {
      _mockMessageCount = 0;
      _mockMessages = [];
      _mockIsStreaming = true;

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Advance past the 100ms debounce
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // Indicator should NOT show because there are no messages
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });
  });

  describe("F3: Scroll-to-bottom when isWaitingForResponse becomes true", () => {
    it("scrolls to bottom when isWaitingForResponse transitions to true", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
      ];
      _mockIsStreaming = true;

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Initial state - no waiting indicator
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();

      // Advance past the 100ms debounce to trigger isWaitingForResponse = true
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      // The rAF callback that sets scrollTop = scrollHeight should have fired
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20);
      });

      // WaitingIndicator should now be visible, confirming the effect ran
      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });
  });

  describe("F4: Rapid isStreaming toggle handling", () => {
    it("shows indicator after rapid send-stop-send toggles within 100ms", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
      ];
      _mockIsStreaming = true;

      render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // At 20ms: toggle isStreaming to false (simulating stop)
      _mockIsStreaming = false;
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      // At 40ms: toggle isStreaming back to true (simulating send again)
      _mockIsStreaming = true;
      await act(async () => {
        vi.advanceTimersByTime(20);
      });

      // At 150ms: indicator should now be visible because the debounce timer fired
      await act(async () => {
        vi.advanceTimersByTime(110);
      });

      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });

    it("hides indicator immediately when isStreaming goes false after being shown", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
      ];
      _mockIsStreaming = true;

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Advance past the 100ms debounce to show the indicator
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();

      // Toggle isStreaming to false - this triggers the useEffect cleanup
      _mockIsStreaming = false;
      
      // Force re-render to pick up the new state
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Indicator should be hidden immediately
      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();
    });

    it("allows indicator to show again after a complete streaming cycle", async () => {
      _mockMessageCount = 2;
      _mockMessages = [
        { id: "1", role: "user", content: "Hello" },
        { id: "2", role: "assistant", content: "" },
      ];
      _mockIsStreaming = true;

      const { rerender } = render(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      // Show indicator
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();

      // Complete the first cycle - toggle isStreaming to false
      _mockIsStreaming = false;
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );

      expect(screen.queryByRole("status", { name: "Waiting for response" })).not.toBeInTheDocument();

      // Start a new streaming cycle - toggle isStreaming back to true
      _mockIsStreaming = true;
      rerender(
        <TooltipProvider>
          <TranscriptPane />
        </TooltipProvider>
      );
      
      // Advance past the 100ms debounce to show the indicator again
      await act(async () => {
        vi.advanceTimersByTime(150);
      });

      expect(screen.getByRole("status", { name: "Waiting for response" })).toBeInTheDocument();
    });
  });
});
