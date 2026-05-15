import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSendMessage } from "./useSendMessage";
import { useChatStore } from "@/stores/useChatStore";
import { useChatShellStore } from "@/stores/useChatShellStore";
import { useLlmHealthStore } from "@/stores/useLlmHealthStore";

const apiMocks = vi.hoisted(() => ({
  createChatSession: vi.fn(),
  addChatMessage: vi.fn(),
  chatStream: vi.fn(),
  getLlmModeHealth: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  createChatSession: (...args: unknown[]) => apiMocks.createChatSession(...args),
  addChatMessage: (...args: unknown[]) => apiMocks.addChatMessage(...args),
  chatStream: (...args: unknown[]) => apiMocks.chatStream(...args),
  getLlmModeHealth: (...args: unknown[]) => apiMocks.getLlmModeHealth(...args),
}));

describe("useSendMessage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      messageIds: [],
      messagesById: {},
      streamingMessageId: null,
      input: "",
      isStreaming: false,
      abortFn: null,
      inputError: null,
      expandedSources: new Set(),
      activeChatId: null,
    });
    useLlmHealthStore.setState({ thinking: true, instant: true });
    useChatShellStore.setState({ sessionListRefreshToken: 0 });
    apiMocks.createChatSession.mockResolvedValue({ id: 42 });
    apiMocks.addChatMessage
      .mockResolvedValueOnce({ id: 100, created_at: "2026-05-12T00:00:00Z" })
      .mockResolvedValueOnce({ id: 101, created_at: "2026-05-12T00:00:01Z" });
    apiMocks.chatStream.mockImplementation((_messages: unknown, handlers: {
      onMessage: (chunk: string) => void;
      onComplete: () => Promise<void>;
    }) => {
      handlers.onMessage("hello");
      void handlers.onComplete();
      return vi.fn();
    });
  });

  it("force-refreshes history after a newly created session is persisted", async () => {
    const refreshHistory = vi.fn().mockResolvedValue(undefined);
    useChatStore.setState({ input: "What changed?" });

    const { result } = renderHook(() => useSendMessage(7, refreshHistory));

    await act(async () => {
      await result.current.handleSend();
    });

    await waitFor(() => {
      expect(refreshHistory).toHaveBeenCalledWith(true);
    });
    expect(useChatShellStore.getState().sessionListRefreshToken).toBeGreaterThan(0);
    expect(apiMocks.createChatSession).toHaveBeenCalledWith({ vault_id: 7 });
    expect(apiMocks.addChatMessage).toHaveBeenCalledWith(42, {
      role: "user",
      content: "What changed?",
    });
  });

  it("force-refreshes history and the session rail after an existing session is persisted", async () => {
    const refreshHistory = vi.fn().mockResolvedValue(undefined);
    useChatStore.setState({ activeChatId: "42", input: "Follow up" });

    const { result } = renderHook(() => useSendMessage(7, refreshHistory));

    await act(async () => {
      await result.current.handleSend();
    });

    await waitFor(() => {
      expect(refreshHistory).toHaveBeenCalledWith(true);
    });
    expect(apiMocks.createChatSession).not.toHaveBeenCalled();
    expect(useChatShellStore.getState().sessionListRefreshToken).toBe(1);
  });

  describe("vault_id defaulting — regression (F#)", () => {
    it("createChatSession uses vault_id=1 when activeVaultId is null", async () => {
      const refreshHistory = vi.fn().mockResolvedValue(undefined);
      useChatStore.setState({ input: "Hello" });

      const { result } = renderHook(() => useSendMessage(null, refreshHistory));

      await act(async () => {
        await result.current.handleSend();
      });

      await waitFor(() => {
        expect(apiMocks.createChatSession).toHaveBeenCalledWith({ vault_id: 1 });
      });
    });

    it("chatStream receives vault_id=1 when activeVaultId is null", async () => {
      const refreshHistory = vi.fn().mockResolvedValue(undefined);
      useChatStore.setState({ input: "Hello" });

      const { result } = renderHook(() => useSendMessage(null, refreshHistory));

      await act(async () => {
        await result.current.handleSend();
      });

      await waitFor(() => {
        // chatStream is called with: (messages, handlers, vault_id, effectiveMode)
        // vault_id is the 3rd argument (index 2)
        expect(apiMocks.chatStream).toHaveBeenCalled();
        const callArgs = apiMocks.chatStream.mock.calls[0];
        expect(callArgs[2]).toBe(1);
      });
    });

    it("chatStream receives the actual activeVaultId when it is non-null", async () => {
      const refreshHistory = vi.fn().mockResolvedValue(undefined);
      useChatStore.setState({ activeChatId: "99", input: "Hello" });

      const { result } = renderHook(() => useSendMessage(5, refreshHistory));

      await act(async () => {
        await result.current.handleSend();
      });

      await waitFor(() => {
        expect(apiMocks.chatStream).toHaveBeenCalled();
        const callArgs = apiMocks.chatStream.mock.calls[0];
        expect(callArgs[2]).toBe(5);
      });
    });

    it("createChatSession receives the actual activeVaultId when it is non-null", async () => {
      const refreshHistory = vi.fn().mockResolvedValue(undefined);
      useChatStore.setState({ input: "Hello" });

      const { result } = renderHook(() => useSendMessage(5, refreshHistory));

      await act(async () => {
        await result.current.handleSend();
      });

      await waitFor(() => {
        expect(apiMocks.createChatSession).toHaveBeenCalledWith({ vault_id: 5 });
      });
    });
  });
});
