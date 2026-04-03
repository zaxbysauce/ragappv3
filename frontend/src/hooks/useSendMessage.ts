import { useCallback, useRef } from "react";
import { chatStream, createChatSession, addChatMessage, type ChatMessage } from "@/lib/api";
import { useChatStore } from "@/stores/useChatStore";

export const MAX_INPUT_LENGTH = 2000;

export interface UseSendMessageReturn {
  handleSend: () => Promise<void>;
  handleStop: () => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
}

/** Handles sending chat messages with streaming, session management, and input validation. */
export function useSendMessage(
  activeVaultId: number | null,
  refreshHistory: () => Promise<void>
): UseSendMessageReturn {
  const {
    setInput,
    setIsStreaming,
    setAbortFn,
    setInputError,
    addMessage,
    updateMessage,
  } = useChatStore();

  // H-4 fix: Atomic guard to prevent double-send on rapid clicks
  const sendingRef = useRef(false);

  const handleSend = useCallback(async () => {
    if (sendingRef.current) return;
    const { input: currentInput, isStreaming: currentIsStreaming } = useChatStore.getState();
    if (!currentInput.trim() || currentIsStreaming) return;
    sendingRef.current = true;
    if (currentInput.length > MAX_INPUT_LENGTH) {
      setInputError(`Input exceeds maximum length of ${MAX_INPUT_LENGTH} characters`);
      return;
    }

    const userContent = currentInput.trim();

    // Get or create session
    const currentState = useChatStore.getState();
    let sessionId: number;

    if (currentState.activeChatId) {
      sessionId = parseInt(currentState.activeChatId);
    } else {
      try {
        const newSession = await createChatSession({ vault_id: activeVaultId ?? 1 });
        sessionId = newSession.id;
        useChatStore.setState({ activeChatId: newSession.id.toString() });
      } catch (err) {
        console.error("Failed to create chat session:", err);
        setInputError("Failed to start chat session. Please check your connection.");
        return;
      }
    }

    const userMessage = {
      id: Date.now().toString(),
      role: "user" as const,
      content: userContent,
    };

    setIsStreaming(true);

    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage = {
      id: assistantMessageId,
      role: "assistant" as const,
      content: "",
    };

    const currentMessages = useChatStore.getState().messages;
    const chatMessages: ChatMessage[] = [
      ...currentMessages.map((m) => ({ role: m.role, content: m.content })),
      { role: "user", content: userMessage.content },
    ];

    // CR-1 fix: Add messages to store BEFORE starting the stream
    // so that onMessage/onSources can find them by ID immediately.
    addMessage(userMessage);
    addMessage(assistantMessage);

    const abort = chatStream(
      chatMessages,
      {
        onMessage: (chunk) => {
          const currentMessages = useChatStore.getState().messages;
          const currentMsg = currentMessages.find((m) => m.id === assistantMessageId);
          updateMessage(assistantMessageId, {
            content: (currentMsg?.content || "") + chunk,
          });
        },
        onSources: (sources) => {
          updateMessage(assistantMessageId, { sources });
        },
        onError: (error) => {
          console.error("Chat stream error:", error);
          updateMessage(assistantMessageId, { error: error.message });
          setIsStreaming(false);
          setAbortFn(null);
          sendingRef.current = false;
        },
        onComplete: async () => {
          setIsStreaming(false);
          setAbortFn(null);
          sendingRef.current = false;
          // Save messages to API
          try {
            // Save user message
            await addChatMessage(sessionId, { role: "user", content: userContent });

            // Save assistant message
            const allMessages = useChatStore.getState().messages;
            const assistantMsg = allMessages.find((m) => m.id === assistantMessageId);
            if (assistantMsg) {
              await addChatMessage(sessionId, {
                role: "assistant",
                content: assistantMsg.content,
                sources: assistantMsg.sources ?? undefined,
              });
            }

            // Refresh session list
            await refreshHistory();
          } catch (err) {
            console.error("Failed to save chat messages:", err);
          }
        },
      },
      activeVaultId ?? undefined
    );

    setAbortFn(abort);

    setInput("");
    setInputError(null);
  }, [
    setInput,
    setIsStreaming,
    setAbortFn,
    setInputError,
    addMessage,
    updateMessage,
    activeVaultId,
    refreshHistory,
  ]);

  const handleStop = useCallback(() => {
    useChatStore.getState().stopStreaming();
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value;
      setInput(value);
      if (value.length > MAX_INPUT_LENGTH) {
        setInputError(`Input exceeds maximum length of ${MAX_INPUT_LENGTH} characters`);
      } else {
        setInputError(null);
      }
    },
    [setInput, setInputError]
  );

  return {
    handleSend,
    handleStop,
    handleKeyDown,
    handleInputChange,
  };
}
