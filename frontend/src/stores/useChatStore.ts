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
  // State
  messages: Message[];
  input: string;
  isStreaming: boolean;
  abortFn: (() => void) | null;
  inputError: string | null;
  expandedSources: Set<string>;
  activeChatId: string | null;

  // Actions
  setMessages: (messages: Message[] | ((prev: Message[]) => Message[])) => void;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  clearMessages: () => void;
  setInput: (input: string) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setAbortFn: (abortFn: (() => void) | null) => void;
  setInputError: (error: string | null) => void;
  toggleSource: (sourceId: string) => void;
  clearExpandedSources: () => void;
  stopStreaming: () => void;
  loadChat: (chatId: string, messages: Message[]) => void;
  newChat: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  // Initial state
  messages: [],
  input: "",
  isStreaming: false,
  abortFn: null,
  inputError: null,
  expandedSources: new Set(),
  activeChatId: null,

  // Actions
  setMessages: (messages) => {
    if (typeof messages === "function") {
      set((state) => ({ messages: messages(state.messages) }));
    } else {
      set({ messages });
    }
  },

  addMessage: (message) => {
    set((state) => ({ messages: [...state.messages, message] }));
  },

  updateMessage: (id, updates) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    }));
  },

  clearMessages: () => {
    set({ messages: [], expandedSources: new Set(), activeChatId: null });
  },

  setInput: (input) => {
    set({ input });
  },

  setIsStreaming: (isStreaming) => {
    set({ isStreaming });
  },

  setAbortFn: (abortFn) => {
    set({ abortFn });
  },

  setInputError: (inputError) => {
    set({ inputError });
  },

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
    const { abortFn } = get();
    if (abortFn) {
      abortFn();
      set({ abortFn: null, isStreaming: false });
      // Mark the last assistant message as stopped
      set((state) => {
        const lastMessage = state.messages[state.messages.length - 1];
        if (lastMessage && lastMessage.role === "assistant") {
          return {
            messages: state.messages.map((msg, idx) =>
              idx === state.messages.length - 1 ? { ...msg, stopped: true } : msg
            ),
          };
        }
        return state;
      });
    }
  },

  loadChat: (chatId, messages) => {
    set({ activeChatId: chatId, messages: messages, expandedSources: new Set() });
  },

  newChat: () => {
    set({ activeChatId: null, messages: [], expandedSources: new Set() });
  },
}));

// H-27: Granular selectors to avoid unnecessary re-renders
export const useChatMessages = () => useChatStore((s) => s.messages);
export const useChatInput = () => useChatStore((s) => s.input);
export const useChatIsStreaming = () => useChatStore((s) => s.isStreaming);
export const useChatInputError = () => useChatStore((s) => s.inputError);
export const useChatActiveChatId = () => useChatStore((s) => s.activeChatId);
