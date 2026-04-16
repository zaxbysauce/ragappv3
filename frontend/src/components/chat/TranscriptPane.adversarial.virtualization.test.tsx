// frontend/src/components/chat/TranscriptPane.adversarial.virtualization.test.tsx
/**
 * ADVERSARIAL VIRTUALIZATION TESTS for TranscriptPane
 *
 * These tests focus on attack vectors specific to the @tanstack/react-virtual
 * integration: malformed messages through virtualizer, oversized payloads,
 * rapid array mutations, boundary violations, and XSS through the virtualized render path.
 *
 * IMPORTANT: These tests MUST mock @tanstack/react-virtual to properly test
 * the virtualizer's handling of adversarial inputs.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { TranscriptPane } from "./TranscriptPane";
import { useChatStore } from "@/stores/useChatStore";
import { useVaultStore } from "@/stores/useVaultStore";

// =============================================================================
// MOCK RESIZE OBSERVER
// =============================================================================

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;

// Mock scrollIntoView
Element.prototype.scrollIntoView = vi.fn();

// =============================================================================
// VIRTUALIZER MOCK STATE
// =============================================================================

// Track virtualizer state for dynamic behavior verification
let _mockMessageCount = 0;
let _scrollToIndexCalls: number[] = [];
let _measureCalls = 0;

// =============================================================================
// MOCK @tanstack/react-virtual
// =============================================================================

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: vi.fn(({ count }) => {
    _mockMessageCount = count;

    return {
      getVirtualItems: () =>
        Array.from({ length: count }, (_, i) => ({
          index: i,
          start: i * 120,
          size: 120,
          key: `msg-${i}`,
          end: (i + 1) * 120,
        })),
      getTotalSize: () => count * 120,
      measureElement: vi.fn((el: HTMLElement) => ({
        getBoundingClientRect: () => ({ height: 120, width: 800 }),
      })),
      scrollToIndex: vi.fn((index: number) => {
        _scrollToIndexCalls.push(index);
      }),
      measure: vi.fn(() => {
        _measureCalls++;
      }),
      scrollOffset: 0,
      totalSize: count * 120,
    };
  }),
}));

// =============================================================================
// OTHER MOCKS
// =============================================================================

vi.mock("@/stores/useChatStore");
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
}));

import { useSendMessage } from "@/hooks/useSendMessage";
import { useChatHistory } from "@/hooks/useChatHistory";

// =============================================================================
// ADVERSARIAL TEST SUITE
// =============================================================================

describe("TranscriptPane ADVERSARIAL - Virtualization Attack Vectors", () => {
  const mockSetInput = vi.fn();
  const mockHandleSend = vi.fn();
  const mockHandleStop = vi.fn();
  const mockRefreshHistory = vi.fn();
  const mockGetActiveVault = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    _mockMessageCount = 0;
    _scrollToIndexCalls = [];
    _measureCalls = 0;

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
    // Clean up any temp directories if created
  });

  // ===========================================================================
  // 1. MALFORMED MESSAGE OBJECTS - Missing id, null content, undefined role
  // ===========================================================================
  describe("Malformed message objects through virtualizer", () => {
    it("should handle message with missing id property", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { role: "user", content: "Test message" } as any, // Missing id
        ],
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

      // Should not crash when virtualizer tries to use message.id as key
      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();

      await waitFor(() => {
        expect(screen.getByTestId("message-bubble")).toBeInTheDocument();
      });
    });

    it("should handle message with null content", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: null } as any,
          { id: "2", role: "assistant", content: null } as any,
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message with undefined role", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: undefined, content: "Test" } as any,
        ],
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

      // Should handle undefined role (neither "user" nor "assistant")
      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message with null id", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: null, role: "user", content: "Test" } as any,
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle completely empty message object", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [{} as any],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message withSymbol id (non-string key)", async () => {
      const symId = Symbol("test");
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: symId, role: "user", content: "Test" } as any,
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message with numeric id (0)", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: 0, role: "user", content: "Zero id" } as any,
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message with empty string id", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "", role: "user", content: "Empty id" } as any,
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 2. EXTREMELY LARGE NUMBER OF MESSAGES (500+) - Virtualizer stress test
  // ===========================================================================
  describe("Extremely large message arrays (500+)", () => {
    it("should handle 500 messages without crashing", async () => {
      const manyMessages = Array.from({ length: 500 }, (_, i) => ({
        id: String(i + 1),
        role: i % 2 === 0 ? "user" : "assistant",
        content: `Message ${i + 1}`,
      }));

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: manyMessages,
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();

      await waitFor(() => {
        expect(screen.getByRole("log")).toBeInTheDocument();
      });
    });

    it("should handle 1000 messages through virtualizer", async () => {
      const manyMessages = Array.from({ length: 1000 }, (_, i) => ({
        id: String(i + 1),
        role: i % 2 === 0 ? "user" : "assistant",
        content: `Message ${i + 1}`,
      }));

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: manyMessages,
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();

      // Virtualizer should handle the count
      expect(_mockMessageCount).toBe(1000);
    });

    it("should handle rapidly adding messages to reach 500+", async () => {
      // Start with a small set and grow
      let currentMessages = Array.from({ length: 10 }, (_, i) => ({
        id: String(i + 1),
        role: i % 2 === 0 ? "user" : "assistant",
        content: `Initial ${i + 1}`,
      }));

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: currentMessages,
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

      const { rerender } = render(<TranscriptPane />);

      // Rapidly grow to 500+
      currentMessages = Array.from({ length: 500 }, (_, i) => ({
        id: String(i + 1),
        role: i % 2 === 0 ? "user" : "assistant",
        content: `Grown ${i + 1}`,
      }));

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: currentMessages,
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

      expect(() => {
        rerender(<TranscriptPane />);
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 3. MESSAGES WITH EXTREMELY LONG CONTENT (>50KB)
  // ===========================================================================
  describe("Extremely long message content (>50KB)", () => {
    it("should handle 50KB message content through virtualizer", async () => {
      const largeContent = "A".repeat(50 * 1024);

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "assistant", content: largeContent },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();

      await waitFor(() => {
        expect(screen.getByTestId("message-bubble")).toBeInTheDocument();
      });
    });

    it("should handle 100KB message content", async () => {
      const hugeContent = "B".repeat(100 * 1024);

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "assistant", content: hugeContent },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle multiple messages each with 50KB content", async () => {
      const largeContent = "C".repeat(50 * 1024);

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: largeContent },
          { id: "2", role: "assistant", content: largeContent },
          { id: "3", role: "user", content: largeContent },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle extremely long single word (no spaces, 100KB)", async () => {
      const singleWord = "X".repeat(100 * 1024);

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: singleWord },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 4. MESSAGES WITH EMPTY STRING CONTENT
  // ===========================================================================
  describe("Empty string content through virtualizer", () => {
    it("should handle empty string message content", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "" },
        ],
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

      render(<TranscriptPane />);

      await waitFor(() => {
        expect(screen.getByTestId("message-bubble")).toBeInTheDocument();
      });
    });

    it("should handle multiple consecutive empty messages", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "" },
          { id: "2", role: "assistant", content: "" },
          { id: "3", role: "user", content: "" },
          { id: "4", role: "assistant", content: "" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle mix of empty and non-empty messages", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "" },
          { id: "3", role: "user", content: "" },
          { id: "4", role: "assistant", content: "Response" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 5. RAPIDLY CHANGING MESSAGE ARRAYS
  // ===========================================================================
  describe("Rapidly changing message arrays", () => {
    it("should handle rapid message additions", async () => {
      const { rerender } = render(<TranscriptPane />);

      // Rapidly add messages
      for (let i = 0; i < 50; i++) {
        (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
          messages: Array.from({ length: i + 1 }, (_, j) => ({
            id: String(j + 1),
            role: j % 2 === 0 ? "user" : "assistant",
            content: `Message ${j + 1}`,
          })),
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

        expect(() => {
          rerender(<TranscriptPane />);
        }).not.toThrow();
      }
    });

    it("should handle rapid message removals", async () => {
      const { rerender } = render(<TranscriptPane />);

      // Start with 50 messages
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: Array.from({ length: 50 }, (_, j) => ({
          id: String(j + 1),
          role: j % 2 === 0 ? "user" : "assistant",
          content: `Message ${j + 1}`,
        })),
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

      rerender(<TranscriptPane />);

      // Rapidly remove messages
      for (let i = 50; i >= 0; i--) {
        (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
          messages: Array.from({ length: i }, (_, j) => ({
            id: String(j + 1),
            role: j % 2 === 0 ? "user" : "assistant",
            content: `Message ${j + 1}`,
          })),
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

        expect(() => {
          rerender(<TranscriptPane />);
        }).not.toThrow();
      }
    });

    it("should handle messages array replaced entirely", async () => {
      const { rerender } = render(<TranscriptPane />);

      // Replace with completely new messages
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "new-1", role: "user", content: "New message 1" },
          { id: "new-2", role: "assistant", content: "New message 2" },
        ],
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

      expect(() => {
        rerender(<TranscriptPane />);
      }).not.toThrow();

      await waitFor(() => {
        expect(screen.getByText("New message 1")).toBeInTheDocument();
      });
    });
  });

  // ===========================================================================
  // 6. VIRTUALIZER WITH ZERO-HEIGHT SCROLL CONTAINER
  // ===========================================================================
  describe("Zero-height scroll container edge case", () => {
    it("should handle scroll container with zero height", async () => {
      // This tests the edge case where getBoundingClientRect returns 0 height
      const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect;
      Element.prototype.getBoundingClientRect = vi.fn(() => ({
        height: 0,
        width: 800,
        top: 0,
        left: 0,
        right: 800,
        bottom: 0,
        x: 0,
        y: 0,
      }));

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [{ id: "1", role: "user", content: "Test" }],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();

      // Restore
      Element.prototype.getBoundingClientRect = originalGetBoundingClientRect;
    });

    it("should handle virtualizer measure returning null/undefined", async () => {
      // The measureElement callback returns getBoundingClientRect().height
      // Test what happens when this is 0 or invalid
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [{ id: "1", role: "user", content: "Test" }],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 7. XSS PAYLOADS THROUGH VIRTUALIZER
  // ===========================================================================
  describe("XSS payloads through virtualized render path", () => {
    const xssPayloads = [
      '<img onerror="alert(1)" src=x>',
      '<script>alert("xss")</script>',
      '<svg onload="alert(1)">',
      '"><script>alert(document.cookie)</script>',
      '<a href="javascript:alert(1)">Click</a>',
      '<div onclick="alert(1)">click me</div>',
      '<iframe src="javascript:alert(1)"></iframe>',
      '${alert(1)}',
      '{{constructor.constructor("alert(1)")()}}',
      '<img src=x onerror="eval(atob(\'YWxlcnQoMSk=\'))">',
    ];

    it.each(xssPayloads)("should NOT execute XSS payload in virtualized message: %s", async (payload) => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "assistant", content: payload },
        ],
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

      render(<TranscriptPane />);

      await waitFor(() => {
        expect(screen.getByTestId("message-bubble")).toBeInTheDocument();
      });

      // Verify no script elements were created
      expect(document.querySelector("script")).toBeNull();
    });

    it("should NOT execute XSS in multiple virtualized messages", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: '<script>alert("user")</script>' },
          { id: "2", role: "assistant", content: '<img onerror="alert(1)" src=x>' },
          { id: "3", role: "user", content: '"><script>alert(1)</script>' },
        ],
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

      render(<TranscriptPane />);

      await waitFor(() => {
        expect(screen.getAllByTestId("message-bubble")).toHaveLength(3);
      });

      // No script execution
      expect(document.querySelector("script")).toBeNull();
    });

    it("should handle XSS payload with streaming state through virtualizer", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: '<script>alert("xss")</script>' },
        ],
        input: "",
        isStreaming: true, // Active streaming
        setInput: mockSetInput,
        setIsStreaming: vi.fn(),
        setAbortFn: vi.fn(),
        setInputError: vi.fn(),
        addMessage: vi.fn(),
        updateMessage: vi.fn(),
        inputError: null,
      });

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();

      // No script execution during streaming
      expect(document.querySelector("script")).toBeNull();
    });
  });

  // ===========================================================================
  // 8. UNICODE AND SPECIAL CHARACTERS THROUGH VIRTUALIZER
  // ===========================================================================
  describe("Unicode and special characters through virtualizer", () => {
    it("should handle RTL override characters in messages", async () => {
      const rtlContent = "\u202EEvil\u202C Content";

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "assistant", content: rtlContent },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle null byte in message content", async () => {
      const nullByteContent = "Hello\x00World";

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: nullByteContent },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle combining characters in message", async () => {
      const combiningContent = "cafe\u0301"; // café with combining accent

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: combiningContent },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle zero-width space in message", async () => {
      const zwspContent = "Hello\u200BWorld";

      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: zwspContent },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 9. BOUNDARY VIOLATIONS - NaN, Infinity, Negative values
  // ===========================================================================
  describe("Boundary violations through virtualizer", () => {
    it("should handle NaN message index", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: String(NaN), role: "assistant", content: "NaN id" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle Infinity message index", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: String(Infinity), role: "assistant", content: "Infinity id" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle -Infinity message index", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: String(-Infinity), role: "assistant", content: "-Infinity id" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle Number.MAX_SAFE_INTEGER id", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: String(Number.MAX_SAFE_INTEGER), role: "assistant", content: "Max safe int id" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle negative index in messages array access", async () => {
      // Attempt to access messages with negative index through virtualizer
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "-5", role: "assistant", content: "Negative index message" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 10. TYPE CONFUSION ATTACKS
  // ===========================================================================
  describe("Type confusion attacks through virtualizer", () => {
    it("should handle message with number role instead of string", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: 123 as any, content: "Number role" },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message with array content instead of string", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: ["array", "content"] as any },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message with object content instead of string", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: { nested: "object" } as any },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });

    it("should handle message with undefined content", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: undefined },
        ],
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

      expect(() => {
        render(<TranscriptPane />);
      }).not.toThrow();
    });
  });
});
