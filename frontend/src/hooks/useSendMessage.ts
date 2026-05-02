import { useCallback, useRef } from "react";
import {
  chatStream,
  createChatSession,
  addChatMessage,
  type ChatMessage,
  type ChatSessionMessage,
} from "@/lib/api";
import { useChatStore, type Message } from "@/stores/useChatStore";
import type { UsedMemory } from "@/lib/api";

export const MAX_INPUT_LENGTH = 2000;

export interface UseSendMessageReturn {
  handleSend: () => Promise<void>;
  handleStop: () => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  /** Send with explicit content + history — does not read or modify composer input state. */
  sendDirect: (content: string, historyMessages: Message[]) => Promise<void>;
}

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
    appendToMessage,
    updateMessage,
    replaceMessageId,
    setStreamingMessageId,
  } = useChatStore();

  // Atomic guard — prevents double-send from rapid clicks / Enter
  const sendingRef = useRef(false);

  /**
   * Core send primitive. Accepts content and a history snapshot directly so
   * it doesn't depend on the Zustand input field at all. Both the normal
   * "send from composer" path and the "retry/sendDirect" path go through here.
   */
  const sendCore = useCallback(
    async (content: string, historyMessages: Message[], clearInput: boolean) => {
      if (sendingRef.current) return;
      sendingRef.current = true;
      setIsStreaming(true);

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
          const status = (err as { response?: { status?: number } })?.response?.status;
          setInputError(
            status === 403
              ? "You don't have permission to chat in this vault."
              : "Failed to start chat session. Please check your connection."
          );
          setIsStreaming(false);
          sendingRef.current = false;
          return;
        }
      }

      const userMessage: Message = {
        id: Date.now().toString(),
        role: "user",
        content,
      };
      const assistantMessageId = (Date.now() + 1).toString();
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: "assistant",
        content: "",
      };

      const chatMessages: ChatMessage[] = [
        ...historyMessages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content },
      ];

      addMessage(userMessage);
      addMessage(assistantMessage);
      setStreamingMessageId(assistantMessageId);

      if (clearInput) {
        setInput("");
        setInputError(null);
      }

      const abort = chatStream(
        chatMessages,
        {
          onMessage: (chunk) => {
            appendToMessage(assistantMessageId, chunk);
          },
          onSources: (sources) => {
            updateMessage(assistantMessageId, { sources });
          },
          onMemories: (memories: UsedMemory[]) => {
            updateMessage(assistantMessageId, { memoriesUsed: memories });
          },
          onError: (error) => {
            console.error("Chat stream error:", error);
            const isAbort =
              error.name === "AbortError" || /aborted|abort/i.test(error.message);
            if (isAbort) {
              setIsStreaming(false);
              setAbortFn(null);
              setStreamingMessageId(null);
              sendingRef.current = false;
              return;
            }
            const isNetworkError =
              /failed to fetch|networkerror|network request failed|load failed/i.test(
                error.message
              );
            const friendlyMessage = isNetworkError
              ? "Connection lost. Check your network and try again."
              : error.message;
            updateMessage(assistantMessageId, { error: friendlyMessage });
            setIsStreaming(false);
            setAbortFn(null);
            setStreamingMessageId(null);
            sendingRef.current = false;
          },
          onComplete: async () => {
            setIsStreaming(false);
            setAbortFn(null);
            setStreamingMessageId(null);
            sendingRef.current = false;
            try {
              const storeState = useChatStore.getState();
              const assistantMsg = storeState.messagesById[assistantMessageId];
              const saves: Promise<ChatSessionMessage>[] = [
                addChatMessage(sessionId, { role: "user", content }),
              ];
              if (assistantMsg) {
                saves.push(
                  addChatMessage(sessionId, {
                    role: "assistant",
                    content: assistantMsg.content,
                    sources: assistantMsg.sources ?? undefined,
                    memories: assistantMsg.memoriesUsed ?? undefined,
                  })
                );
              }
              const [userSaveResult, assistantSaveResult] = await Promise.all(saves);

              // Atomically migrate temp client IDs to DB-assigned IDs.
              // Uses replaceMessageId so messageIds, messagesById, and
              // streamingMessageId remain consistent. Migrates the local
              // feedback storage key alongside the ID swap.
              const migrateId = (oldId: string, saveResult: ChatSessionMessage) => {
                const dbId = String(saveResult.id);
                if (dbId === oldId) return;
                const feedbackKey = `chat_feedback_${oldId}`;
                const feedbackValue = localStorage.getItem(feedbackKey);
                if (feedbackValue !== null) {
                  localStorage.setItem(`chat_feedback_${dbId}`, feedbackValue);
                  localStorage.removeItem(feedbackKey);
                }
                replaceMessageId(oldId, dbId, { created_at: saveResult.created_at });
              };

              migrateId(userMessage.id, userSaveResult);
              if (assistantSaveResult) migrateId(assistantMessageId, assistantSaveResult);

              await refreshHistory();
            } catch (err) {
              console.error("Failed to save chat messages:", err);
            }
          },
        },
        activeVaultId ?? undefined
      );

      setAbortFn(abort);
    },
    [
      setInput,
      setIsStreaming,
      setAbortFn,
      setInputError,
      addMessage,
      appendToMessage,
      updateMessage,
      replaceMessageId,
      setStreamingMessageId,
      activeVaultId,
      refreshHistory,
    ]
  );

  /** Normal send — reads content from the Zustand input field. */
  const handleSend = useCallback(async () => {
    const { input: currentInput, isStreaming: currentIsStreaming } =
      useChatStore.getState();
    if (!currentInput.trim() || currentIsStreaming || sendingRef.current) return;
    if (currentInput.length > MAX_INPUT_LENGTH) {
      setInputError(`Input exceeds maximum length of ${MAX_INPUT_LENGTH} characters`);
      return;
    }
    const content = currentInput.trim();
    const { messageIds, messagesById } = useChatStore.getState();
    const history = messageIds.map((id) => messagesById[id]);
    await sendCore(content, history, true);
  }, [setInputError, sendCore]);

  /**
   * Direct send — accepts content and history explicitly.
   * Used for retry / regenerate so it doesn't touch the composer input.
   */
  const sendDirect = useCallback(
    async (content: string, historyMessages: Message[]) => {
      const { isStreaming: currentIsStreaming } = useChatStore.getState();
      if (currentIsStreaming || sendingRef.current) return;
      await sendCore(content, historyMessages, false);
    },
    [sendCore]
  );

  const handleStop = useCallback(() => {
    useChatStore.getState().stopStreaming();
    sendingRef.current = false;
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // IME guard: don't send while composing CJK or other multi-key input
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
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

  return { handleSend, handleStop, handleKeyDown, handleInputChange, sendDirect };
}
