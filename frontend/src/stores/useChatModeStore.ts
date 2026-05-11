import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ChatMode = "instant" | "thinking";

interface ChatModeState {
  /** User-pinned mode. `null` means "use the settings default". */
  chatMode: ChatMode | null;
  setChatMode: (mode: ChatMode) => void;
  clearChatMode: () => void;
}

export const useChatModeStore = create<ChatModeState>()(
  persist(
    (set) => ({
      chatMode: null,
      setChatMode: (chatMode) => set({ chatMode }),
      clearChatMode: () => set({ chatMode: null }),
    }),
    { name: "ragapp_chat_mode" }
  )
);
