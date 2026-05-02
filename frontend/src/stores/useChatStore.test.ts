import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "./useChatStore";

beforeEach(() => {
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
});

describe("replaceMessageId", () => {
  it("replaces id in messageIds preserving order", () => {
    const s = useChatStore.getState();
    s.addMessage({ id: "a", role: "user", content: "hi" });
    s.addMessage({ id: "b", role: "assistant", content: "hello" });
    s.addMessage({ id: "c", role: "user", content: "next" });
    s.replaceMessageId("b", "B-99");
    const after = useChatStore.getState();
    expect(after.messageIds).toEqual(["a", "B-99", "c"]);
    expect(after.messagesById["B-99"]).toBeDefined();
    expect(after.messagesById["b"]).toBeUndefined();
    expect(after.messagesById["B-99"].content).toBe("hello");
    expect(after.messagesById["B-99"].id).toBe("B-99");
  });

  it("merges optional updates atomically", () => {
    const s = useChatStore.getState();
    s.addMessage({ id: "x", role: "assistant", content: "" });
    s.replaceMessageId("x", "42", { created_at: "2025-01-01", content: "final" });
    const after = useChatStore.getState();
    expect(after.messagesById["42"].content).toBe("final");
    expect(after.messagesById["42"].created_at).toBe("2025-01-01");
  });

  it("updates streamingMessageId when it points at oldId", () => {
    const s = useChatStore.getState();
    s.addMessage({ id: "stream-1", role: "assistant", content: "" });
    s.setStreamingMessageId("stream-1");
    s.replaceMessageId("stream-1", "db-7");
    const after = useChatStore.getState();
    expect(after.streamingMessageId).toBe("db-7");
  });

  it("preserves feedback after replacement", () => {
    const s = useChatStore.getState();
    s.addMessage({
      id: "old",
      role: "assistant",
      content: "x",
      feedback: "up",
    });
    s.replaceMessageId("old", "new", { created_at: "t" });
    const after = useChatStore.getState();
    expect(after.messagesById["new"].feedback).toBe("up");
  });

  it("is a no-op when oldId is missing", () => {
    const s = useChatStore.getState();
    s.addMessage({ id: "k", role: "user", content: "v" });
    s.replaceMessageId("missing", "new");
    const after = useChatStore.getState();
    expect(after.messageIds).toEqual(["k"]);
    expect(after.messagesById["new"]).toBeUndefined();
  });

  it("merges in place when oldId === newId", () => {
    const s = useChatStore.getState();
    s.addMessage({ id: "same", role: "assistant", content: "old" });
    s.replaceMessageId("same", "same", { content: "new" });
    const after = useChatStore.getState();
    expect(after.messagesById["same"].content).toBe("new");
    expect(after.messageIds).toEqual(["same"]);
  });

  it("rejects when newId already exists to avoid corruption", () => {
    const s = useChatStore.getState();
    s.addMessage({ id: "a", role: "user", content: "1" });
    s.addMessage({ id: "b", role: "user", content: "2" });
    s.replaceMessageId("a", "b");
    const after = useChatStore.getState();
    // Both still present, ordering unchanged.
    expect(after.messageIds).toEqual(["a", "b"]);
    expect(after.messagesById["a"].content).toBe("1");
    expect(after.messagesById["b"].content).toBe("2");
  });
});
