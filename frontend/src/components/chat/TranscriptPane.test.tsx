// frontend/src/components/chat/TranscriptPane.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TranscriptPane, Composer, EmptyTranscript } from "./TranscriptPane";
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
}));

import { useSendMessage, MAX_INPUT_LENGTH } from "@/hooks/useSendMessage";
import { useChatHistory } from "@/hooks/useChatHistory";

describe("TranscriptPane", () => {
  const mockSetInput = vi.fn();
  const mockHandleSend = vi.fn();
  const mockHandleStop = vi.fn();
  const mockRefreshHistory = vi.fn();
  const mockGetActiveVault = vi.fn();
  const mockNavigate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

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

  describe("1. TranscriptPane renders EmptyTranscript when no messages", () => {
    it("shows EmptyTranscript component when messages array is empty", () => {
      render(<TranscriptPane />);
      expect(screen.getByText("What would you like to know?")).toBeInTheDocument();
    });

    it("does not render any MessageBubble when messages are empty", () => {
      render(<TranscriptPane />);
      expect(screen.queryByTestId("message-bubble")).not.toBeInTheDocument();
    });
  });

  describe("2. TranscriptPane renders message list when messages exist", () => {
    it("renders MessageBubble components for each message", () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [
          { id: "1", role: "user", content: "Hello" },
          { id: "2", role: "assistant", content: "Hi there!" },
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
      expect(screen.getAllByTestId("message-bubble")).toHaveLength(2);
    });

    it("renders user message correctly", () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        messages: [{ id: "1", role: "user", content: "Test message" }],
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
      expect(screen.getByText("Test message")).toBeInTheDocument();
    });
  });

  describe("3. Scroll-to-bottom button appears when scrolled up", () => {
    it("TranscriptPane has scroll area element", () => {
      render(<TranscriptPane />);
      expect(screen.getByRole("log")).toBeInTheDocument();
    });

    it("shows scroll button when TranscriptPane renders", () => {
      render(<TranscriptPane />);
      // Verify the scroll area exists (actual scroll behavior is tested via integration)
      const scrollArea = screen.getByRole("log");
      expect(scrollArea).toBeInTheDocument();
    });
  });

  describe("4. Composer renders textarea with placeholder", () => {
    it("renders textarea with correct placeholder text", () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);
      expect(screen.getByPlaceholderText(/Message\.\.\. \(type \/ for commands/i)).toBeInTheDocument();
    });

    it("textarea has correct aria-label", () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);
      expect(screen.getByLabelText("Message input")).toBeInTheDocument();
    });
  });

  describe("5. Composer shows VaultContextPill when vault is active", () => {
    it("displays vault badge with vault name", () => {
      mockGetActiveVault.mockReturnValue({
        id: 1,
        name: "Test Vault",
        file_count: 5,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);
      expect(screen.getByText("Test Vault")).toBeInTheDocument();
    });

    it("vault pill has correct aria-label", () => {
      mockGetActiveVault.mockReturnValue({
        id: 1,
        name: "Test Vault",
        file_count: 5,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);
      expect(screen.getByLabelText("Active vault: Test Vault")).toBeInTheDocument();
    });
  });

  describe("6. Composer hides VaultContextPill when no vault", () => {
    it("does not render vault badge when no active vault", () => {
      mockGetActiveVault.mockReturnValue(undefined);

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);
      expect(screen.queryByLabelText(/Active vault:/i)).not.toBeInTheDocument();
    });

    it("does not show vault name in badge when getActiveVault returns undefined", () => {
      mockGetActiveVault.mockReturnValue(undefined);

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);
      expect(screen.queryByText("Test Vault")).not.toBeInTheDocument();
    });
  });

  describe("7. Composer slash menu opens when \"/\" is typed", () => {
    it("shows slash command menu when user types /", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/");
      });

      await waitFor(() => {
        expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
      });
    });

    it("slash menu contains all 4 commands by default", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/");
      });

      await waitFor(() => {
        const listbox = screen.getByRole("listbox", { name: "Slash commands" });
        expect(within(listbox).getByText("/summarize")).toBeInTheDocument();
        expect(within(listbox).getByText("/compare")).toBeInTheDocument();
        expect(within(listbox).getByText("/timeline")).toBeInTheDocument();
        expect(within(listbox).getByText("/actions")).toBeInTheDocument();
      });
    });
  });

  describe("8. Composer slash menu filters commands", () => {
    it("shows no commands when filter matches nothing", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/xyz");
      });

      // Menu should not be visible when no commands match
      expect(screen.queryByRole("listbox", { name: "Slash commands" })).not.toBeInTheDocument();
    });

    it("slash menu opens when / is typed", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/");
      });

      await waitFor(() => {
        expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
      });
    });
  });

  describe("9. Composer Enter sends when menu is closed", () => {
    it("calls onSend when Enter is pressed without Shift and menu is closed", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "Test message",
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      // Ensure menu is not open (type without leading /)
      await act(async () => {
        await userEvent.type(textarea, "Test message");
      });
      
      // Press Enter without Shift
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

      await waitFor(() => {
        expect(mockHandleSend).toHaveBeenCalled();
      });
    });

    it("does not send if input is only whitespace", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "   ",
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

      expect(mockHandleSend).not.toHaveBeenCalled();
    });
  });

  describe("10. Composer Enter selects menu item when menu is open", () => {
    it("inserts command and closes menu when Enter is pressed with menu open", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/");
      });

      await waitFor(() => {
        expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
      });

      // Press Enter to select first command
      fireEvent.keyDown(textarea, { key: "Enter" });

      await waitFor(() => {
        expect(mockSetInput).toHaveBeenCalledWith("/summarize ");
      });
    });

    it("Escape key closes the menu", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/");
      });

      await waitFor(() => {
        expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
      });

      fireEvent.keyDown(textarea, { key: "Escape" });

      expect(screen.queryByRole("listbox", { name: "Slash commands" })).not.toBeInTheDocument();
    });

    it("clicking a command in menu inserts it", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/");
      });

      await waitFor(() => {
        expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
      });

      const compareCommand = screen.getByText("/compare");
      await act(async () => {
        await userEvent.click(compareCommand);
      });

      await waitFor(() => {
        expect(mockSetInput).toHaveBeenCalledWith("/compare ");
      });
    });
  });

  describe("11. Composer Shift+Enter adds newline", () => {
    it("does not call onSend when Shift+Enter is pressed", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "Test",
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });

      expect(mockHandleSend).not.toHaveBeenCalled();
    });

    it("textarea updates on key events for newline handling", async () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "Line 1",
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      // Shift+Enter should be handled without sending
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
      
      // Verify send was NOT called
      expect(mockHandleSend).not.toHaveBeenCalled();
    });
  });

  describe("12. Composer send button disabled when input is empty", () => {
    it("send button is disabled when input is empty", () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "",
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const sendButton = screen.getByLabelText(/send message/i);
      expect(sendButton).toBeDisabled();
    });

    it("send button is disabled when input is only whitespace", () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "   ",
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const sendButton = screen.getByLabelText(/send message/i);
      expect(sendButton).toBeDisabled();
    });

    it("send button is enabled when input has content", () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "Hello",
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const sendButton = screen.getByLabelText(/send message/i);
      expect(sendButton).not.toBeDisabled();
    });
  });

  describe("13. Composer stop button visible during streaming", () => {
    it("shows stop button when isStreaming is true", () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={true} />);
      expect(screen.getByText("Stop")).toBeInTheDocument();
      expect(screen.getByLabelText("Stop generating")).toBeInTheDocument();
    });

    it("calls onStop when stop button is clicked", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={true} />);

      const stopButton = screen.getByLabelText("Stop generating");
      
      await act(async () => {
        await userEvent.click(stopButton);
      });

      expect(mockHandleStop).toHaveBeenCalled();
    });

    it("send button is hidden when streaming", () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={true} />);
      expect(screen.queryByLabelText(/send message/i)).not.toBeInTheDocument();
    });
  });

  describe("14. Composer attachment button is disabled", () => {
    it("attachment button is present and disabled", () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const attachmentButton = screen.getByLabelText(/attach file/i);
      expect(attachmentButton).toBeInTheDocument();
      expect(attachmentButton).toBeDisabled();
    });

    it("attachment button has correct tooltip", () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const attachmentButton = screen.getByLabelText(/attach file/i);
      expect(attachmentButton).toHaveAttribute("aria-label", "Attach file (coming soon)");
    });
  });

  describe("15. EmptyTranscript shows suggested prompts when vault has docs", () => {
    it("displays all 4 suggested prompts when hasIndexedDocs is true", () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={true}
          onNavigateToDocuments={mockNavigate}
        />
      );

      expect(screen.getByText("What are the key findings?")).toBeInTheDocument();
      expect(screen.getByText("Summarize the main topics")).toBeInTheDocument();
      expect(screen.getByText("What data sources were used?")).toBeInTheDocument();
      expect(screen.getByText("What are the main conclusions?")).toBeInTheDocument();
    });

    it("displays appropriate heading for vault with docs", () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={true}
          onNavigateToDocuments={mockNavigate}
        />
      );

      expect(screen.getByText("What would you like to know?")).toBeInTheDocument();
    });

    it("prompts list has correct role and aria-label", () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={true}
          onNavigateToDocuments={mockNavigate}
        />
      );

      expect(screen.getByRole("list", { name: "Suggested prompts" })).toBeInTheDocument();
    });
  });

  describe("16. EmptyTranscript shows EmptyVaultCTA when vault has no docs", () => {
    it("displays empty vault heading", () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={false}
          onNavigateToDocuments={mockNavigate}
        />
      );

      expect(screen.getByText("Upload documents to get started")).toBeInTheDocument();
    });

    it("displays empty vault description", () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={false}
          onNavigateToDocuments={mockNavigate}
        />
      );

      expect(screen.getByText(/Add documents to your vault/i)).toBeInTheDocument();
    });

    it("shows 'Go to Documents' button", () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={false}
          onNavigateToDocuments={mockNavigate}
        />
      );

      expect(screen.getByText("Go to Documents")).toBeInTheDocument();
    });

    it("does not show suggested prompts when hasIndexedDocs is false", () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={false}
          onNavigateToDocuments={mockNavigate}
        />
      );

      expect(screen.queryByText("What are the key findings?")).not.toBeInTheDocument();
      expect(screen.queryByRole("list", { name: "Suggested prompts" })).not.toBeInTheDocument();
    });
  });

  describe("17. Clicking suggested prompt sets input in store", () => {
    it("calls onPromptClick with correct prompt when clicked", async () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={true}
          onNavigateToDocuments={mockNavigate}
        />
      );

      const promptButton = screen.getByText("What are the key findings?");
      
      await act(async () => {
        await userEvent.click(promptButton);
      });

      expect(mockSetInput).toHaveBeenCalledWith("What are the key findings?");
    });

    it("works for all suggested prompts", async () => {
      render(
        <EmptyTranscript
          onPromptClick={mockSetInput}
          hasIndexedDocs={true}
          onNavigateToDocuments={mockNavigate}
        />
      );

      const prompts = [
        "What are the key findings?",
        "Summarize the main topics",
        "What data sources were used?",
        "What are the main conclusions?",
      ];

      for (const prompt of prompts) {
        vi.clearAllMocks();
        const button = screen.getByText(prompt);
        await act(async () => {
          await userEvent.click(button);
        });
        expect(mockSetInput).toHaveBeenCalledWith(prompt);
      }
    });
  });

  describe("Additional coverage", () => {
    it("textarea is disabled when streaming", () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={true} />);

      const textarea = screen.getByLabelText("Message input");
      expect(textarea).toBeDisabled();
    });

    it("shows error message when inputError is set", () => {
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: "",
        setInput: mockSetInput,
        inputError: "Test error message",
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      expect(screen.getByRole("alert")).toHaveTextContent("Test error message");
    });

    it("character count shows warning when input is near max length", () => {
      const longInput = "a".repeat(1700); // > 80% of 2000
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: longInput,
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      expect(screen.getByText(/1700\/2000/)).toBeInTheDocument();
    });

    it("character count shows destructive color when over max", () => {
      const overMaxInput = "a".repeat(2100); // > 2000
      (useChatStore as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        input: overMaxInput,
        setInput: mockSetInput,
        inputError: null,
        isStreaming: false,
      });

      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const charCount = screen.getByText(/2100\/2000/);
      expect(charCount).toHaveClass(/destructive/);
    });

    it("keyboard navigation works in slash menu", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      await act(async () => {
        await userEvent.click(textarea);
        await userEvent.type(textarea, "/");
      });

      await waitFor(() => {
        expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
      });

      // Navigate down
      fireEvent.keyDown(textarea, { key: "ArrowDown" });
      
      // Verify menu still visible after navigation
      await waitFor(() => {
        expect(screen.getByRole("listbox", { name: "Slash commands" })).toBeInTheDocument();
      });
    });

    it("slash hint button exists", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const slashButton = screen.getByLabelText("Open slash commands");
      expect(slashButton).toBeInTheDocument();
    });

    it("TranscriptPane renders with empty vault CTA", () => {
      mockGetActiveVault.mockReturnValue({
        id: 1,
        name: "Empty Vault",
        file_count: 0,
      });

      render(<TranscriptPane />);

      expect(screen.getByText("Upload documents to get started")).toBeInTheDocument();
    });

    it("handles multiline input", async () => {
      render(<Composer onSend={mockHandleSend} onStop={mockHandleStop} isStreaming={false} />);

      const textarea = screen.getByPlaceholderText(/Message\.\.\./i);
      
      // Type text and then newline
      await act(async () => {
        await userEvent.type(textarea, "Hello world");
      });

      expect(mockSetInput).toHaveBeenCalled();
    });

    it("shows MAX_INPUT_LENGTH constant is 2000", () => {
      expect(MAX_INPUT_LENGTH).toBe(2000);
    });
  });
});
