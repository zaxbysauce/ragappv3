import { create } from "zustand";
import type { Source } from "@/lib/api";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  stopped?: boolean;
  error?: string;
  created_at?: string;
  feedback?: "up" | "down" | null;
}

export interface ChatState {
  // Normalized message storage — O(1) streaming updates on the active message
  messageIds: string[];
  messagesById: Record<string, Message>;
  streamingMessageId: string | null;

  input: string;
  isStreaming: boolean;
  abortFn: (() => void) | null;
  inputError: string | null;
  expandedSources: Set<string>;
  activeChatId: string | null;

  // Actions
  addMessage: (message: Message) => void;
  /** Fast streaming path: appends a chunk to content without replacing the full array. */
  appendToMessage: (id: string, chunk: string) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  /** Trim messages array at the given index (exclusive). */
  removeMessagesFrom: (index: number) => void;
  clearMessages: () => void;
  setInput: (input: string) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setStreamingMessageId: (id: string | null) => void;
  setAbortFn: (abortFn: (() => void) | null) => void;
  setInputError: (error: string | null) => void;
  toggleSource: (sourceId: string) => void;
  clearExpandedSources: () => void;
  stopStreaming: () => void;
  loadChat: (chatId: string, messages: Message[]) => void;
  newChat: () => void;

  // Legacy compat — converts array to/from normalized shape
  setMessages: (messages: Message[] | ((prev: Message[]) => Message[])) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messageIds: [],
  messagesById: {},
  streamingMessageId: null,
  input: "",
  isStreaming: false,
  abortFn: null,
  inputError: null,
  expandedSources: new Set(),
  activeChatId: null,

  addMessage: (message) => {
    set((state) => ({
      messageIds: [...state.messageIds, message.id],
      messagesById: { ...state.messagesById, [message.id]: message },
    }));
  },

  appendToMessage: (id, chunk) => {
    set((state) => {
      const msg = state.messagesById[id];
      if (!msg) return state;
      return {
        messagesById: {
          ...state.messagesById,
          [id]: { ...msg, content: msg.content + chunk },
        },
      };
    });
  },

  updateMessage: (id, updates) => {
    set((state) => {
      const msg = state.messagesById[id];
      if (!msg) return state;
      return {
        messagesById: {
          ...state.messagesById,
          [id]: { ...msg, ...updates },
        },
      };
    });
  },

  removeMessagesFrom: (index) => {
    set((state) => {
      const newIds = state.messageIds.slice(0, index);
      const newById: Record<string, Message> = {};
      for (const id of newIds) {
        if (state.messagesById[id]) newById[id] = state.messagesById[id];
      }
      return { messageIds: newIds, messagesById: newById };
    });
  },

  clearMessages: () => {
    set({ messageIds: [], messagesById: {}, expandedSources: new Set(), activeChatId: null, streamingMessageId: null });
  },

  setInput: (input) => set({ input }),
  setIsStreaming: (isStreaming) => set({ isStreaming }),
  setStreamingMessageId: (streamingMessageId) => set({ streamingMessageId }),
  setAbortFn: (abortFn) => set({ abortFn }),
  setInputError: (inputError) => set({ inputError }),

  toggleSource: (sourceId) => {
    set((state) => {
      const newSet = new Set(state.expandedSources);
      if (newSet.has(sourceId)) {
        newSet.delete(sourceId);
      } else {
        newSet.add(sourceId);
      }
      return { expandedSources: newSet };
    });
  },

  clearExpandedSources: () => {
    set({ expandedSources: new Set() });
  },

  stopStreaming: () => {
    const { abortFn, messageIds, messagesById, streamingMessageId } = get();
    if (abortFn) abortFn();

    const updates: Partial<ChatState> = {
      abortFn: null,
      isStreaming: false,
      streamingMessageId: null,
    };

    const targetId = streamingMessageId ?? messageIds[messageIds.length - 1];
    if (targetId) {
      const lastMsg = messagesById[targetId];
      if (lastMsg && lastMsg.role === "assistant") {
        updates.messagesById = {
          ...messagesById,
          [targetId]: { ...lastMsg, stopped: true },
        };
      }
    }
    set(updates);
  },

  loadChat: (chatId, messages) => {
    const messageIds = messages.map((m) => m.id);
    const messagesById: Record<string, Message> = {};
    for (const m of messages) messagesById[m.id] = m;
    set({ activeChatId: chatId, messageIds, messagesById, expandedSources: new Set(), streamingMessageId: null });
  },

  newChat: () => {
    set({ activeChatId: null, messageIds: [], messagesById: {}, expandedSources: new Set(), streamingMessageId: null });
  },

  setMessages: (messages) => {
    const current = get();
    const resolved =
      typeof messages === "function"
        ? messages(current.messageIds.map((id) => current.messagesById[id]))
        : messages;
    const newIds = resolved.map((m) => m.id);
    const newById: Record<string, Message> = {};
    for (const m of resolved) newById[m.id] = m;
    set({ messageIds: newIds, messagesById: newById });
  },
}));

// Selectors — use granular selectors to limit re-renders
export const useMessageIds = () => useChatStore((s) => s.messageIds);
/** Subscribe to a single message by ID — streaming rows only re-render for their own message. */
export const useMessage = (id: string) => useChatStore((s) => s.messagesById[id]);
/** Legacy: full messages array. Triggers re-render when any message changes. */
export const useChatMessages = () =>
  useChatStore((s) => s.messageIds.map((id) => s.messagesById[id]));
export const useChatInput = () => useChatStore((s) => s.input);
export const useChatIsStreaming = () => useChatStore((s) => s.isStreaming);
export const useChatInputError = () => useChatStore((s) => s.inputError);
export const useChatActiveChatId = () => useChatStore((s) => s.activeChatId);
export const useChatStreamingId = () => useChatStore((s) => s.streamingMessageId);
