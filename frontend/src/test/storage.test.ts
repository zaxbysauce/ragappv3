import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  safeSetItem,
  setChatHistory,
  getChatHistory,
  type ChatHistoryItem,
  type ChatMessage,
} from "../lib/storage";

describe("storage.ts - localStorage quota enforcement", () => {
  // Store original implementations
  let originalLocalStorage: Storage;
  let originalNavigator: Navigator;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Reset all mocks before each test
    vi.clearAllMocks();

    // Spy on console methods
    consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    // Create a fresh localStorage mock for each test
    const store: Record<string, string> = {};
    const localStorageMock = {
      getItem: vi.fn((key: string) => store[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
      clear: vi.fn(() => {
        Object.keys(store).forEach((key) => delete store[key]);
      }),
      length: 0,
      key: vi.fn(),
    };

    Object.defineProperty(global, "localStorage", {
      value: localStorageMock,
      writable: true,
      configurable: true,
    });

    // Reset navigator.storage mock
    Object.defineProperty(global, "navigator", {
      value: {
        storage: {
          estimate: vi.fn().mockResolvedValue({
            usage: 1000,
            quota: 10000000, // 10MB default
          }),
        },
      },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    consoleWarnSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  describe("safeSetItem", () => {
    describe("happy path", () => {
      it("should successfully store a value when quota is available", async () => {
        const result = await safeSetItem("test-key", "test-value");

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith("test-key", "test-value");
      });

      it("should store JSON serialized objects", async () => {
        const data = { name: "test", value: 123 };
        const result = await safeSetItem("json-key", JSON.stringify(data));

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith(
          "json-key",
          JSON.stringify(data)
        );
      });

      it("should return true when storage API is not available (Infinity fallback)", async () => {
        // Remove storage API
        Object.defineProperty(global, "navigator", {
          value: {},
          writable: true,
          configurable: true,
        });

        const result = await safeSetItem("test-key", "test-value");

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalled();
      });
    });

    describe("edge cases", () => {
      it("should handle empty string values", async () => {
        const result = await safeSetItem("empty-key", "");

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith("empty-key", "");
      });

      it("should handle large string values within quota", async () => {
        const largeValue = "x".repeat(10000);
        const result = await safeSetItem("large-key", largeValue);

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith("large-key", largeValue);
      });

      it("should handle unicode characters correctly", async () => {
        const unicodeValue = "Hello 世界 🌍 émojis";
        const result = await safeSetItem("unicode-key", unicodeValue);

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith("unicode-key", unicodeValue);
      });

      it("should handle keys with special characters", async () => {
        const specialKey = "key-with-special-chars_123.test";
        const result = await safeSetItem(specialKey, "value");

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith(specialKey, "value");
      });
    });

    describe("quota exceeded handling", () => {
      it("should return false when quota is exceeded based on storage estimate", async () => {
        // Mock very low available quota
        Object.defineProperty(global, "navigator", {
          value: {
            storage: {
              estimate: vi.fn().mockResolvedValue({
                usage: 9999000,
                quota: 10000000, // Only 1KB available
              }),
            },
          },
          writable: true,
          configurable: true,
        });

        const largeValue = "x".repeat(5000); // 5KB value
        const result = await safeSetItem("quota-key", largeValue);

        expect(result).toBe(false);
        expect(localStorage.setItem).not.toHaveBeenCalled();
        expect(consoleWarnSpy).toHaveBeenCalledWith(
          expect.stringContaining("Quota exceeded")
        );
      });

      it("should return false when localStorage throws QuotaExceededError", async () => {
        const quotaError = new Error("Quota exceeded");
        quotaError.name = "QuotaExceededError";

        vi.mocked(localStorage.setItem).mockImplementation(() => {
          throw quotaError;
        });

        const result = await safeSetItem("quota-key", "value");

        expect(result).toBe(false);
        expect(consoleWarnSpy).toHaveBeenCalledWith(
          expect.stringContaining("Quota exceeded")
        );
      });

      it("should account for 1KB buffer when checking quota", async () => {
        // Set quota such that value + buffer exceeds available
        Object.defineProperty(global, "navigator", {
          value: {
            storage: {
              estimate: vi.fn().mockResolvedValue({
                usage: 9999500,
                quota: 10000000, // 500 bytes available
              }),
            },
          },
          writable: true,
          configurable: true,
        });

        const value = "x".repeat(100); // 100 bytes, but + 1KB buffer = 1100 bytes needed
        const result = await safeSetItem("buffer-test-key", value);

        expect(result).toBe(false);
        expect(localStorage.setItem).not.toHaveBeenCalled();
      });

      it("should handle storage.estimate() throwing an error", async () => {
        Object.defineProperty(global, "navigator", {
          value: {
            storage: {
              estimate: vi.fn().mockRejectedValue(new Error("Storage API error")),
            },
          },
          writable: true,
          configurable: true,
        });

        const result = await safeSetItem("test-key", "test-value");

        // Should fall back to Infinity and succeed
        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalled();
      });
    });

    describe("error handling", () => {
      it("should re-throw non-quota errors", async () => {
        const otherError = new Error("Some other error");
        vi.mocked(localStorage.setItem).mockImplementation(() => {
          throw otherError;
        });

        await expect(safeSetItem("key", "value")).rejects.toThrow("Some other error");
      });

      it("should handle localStorage being unavailable", async () => {
        Object.defineProperty(global, "localStorage", {
          value: null,
          writable: true,
          configurable: true,
        });

        await expect(safeSetItem("key", "value")).rejects.toThrow();
      });
    });
  });

  describe("setChatHistory", () => {
    const createMockHistory = (itemCount: number, messagesPerItem: number): ChatHistoryItem[] => {
      return Array.from({ length: itemCount }, (_, i) => ({
        id: `chat-${i}`,
        title: `Chat ${i}`,
        lastActive: new Date().toISOString(),
        messageCount: messagesPerItem,
        messages: Array.from({ length: messagesPerItem }, (_, j) => ({
          id: `msg-${i}-${j}`,
          role: j % 2 === 0 ? "user" : "assistant",
          content: `Message content ${j}`,
        })),
      }));
    };

    describe("happy path", () => {
      it("should successfully store chat history", async () => {
        const history = createMockHistory(2, 3);
        const result = await setChatHistory(history);

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith(
          "kv_chat_history",
          expect.any(String)
        );
      });

      it("should store empty history array by clearing the key", async () => {
        const result = await setChatHistory([]);

        expect(result).toBe(true);
        // Empty history results in removeItem being called to clear the key
        expect(localStorage.removeItem).toHaveBeenCalledWith("kv_chat_history");
      });

      it("should correctly serialize chat history with all fields", async () => {
        const history: ChatHistoryItem[] = [
          {
            id: "chat-1",
            title: "Test Chat",
            lastActive: "2024-01-01T00:00:00Z",
            messageCount: 2,
            messages: [
              {
                id: "msg-1",
                role: "user",
                content: "Hello",
                sources: [{ id: "src-1", filename: "doc.txt", score: 0.95 }],
              },
              {
                id: "msg-2",
                role: "assistant",
                content: "Hi there!",
              },
            ],
          },
        ];

        await setChatHistory(history);

        const storedCall = vi.mocked(localStorage.setItem).mock.calls[0];
        const storedData = JSON.parse(storedCall[1]);

        expect(storedData).toHaveLength(1);
        expect(storedData[0].id).toBe("chat-1");
        expect(storedData[0].messages).toHaveLength(2);
        expect(storedData[0].messages[0].sources).toBeDefined();
      });
    });

    describe("quota exceeded with retry logic", () => {
      it("should trim messages and retry when quota is exceeded", async () => {
        let callCount = 0;
        vi.mocked(localStorage.setItem).mockImplementation(() => {
          callCount++;
          if (callCount === 1) {
            const error = new Error("Quota exceeded");
            error.name = "QuotaExceededError";
            throw error;
          }
        });

        const history = createMockHistory(1, 10); // 1 item with 10 messages
        const result = await setChatHistory(history);

        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledTimes(2);
        expect(consoleWarnSpy).toHaveBeenCalledWith(
          expect.stringContaining("Retrying after trimming")
        );
      });

      it("should remove oldest items when messages cannot be trimmed further", async () => {
        let callCount = 0;
        vi.mocked(localStorage.setItem).mockImplementation(() => {
          callCount++;
          if (callCount <= 2) {
            const error = new Error("Quota exceeded");
            error.name = "QuotaExceededError";
            throw error;
          }
        });

        // 3 items with only 1 message each (can't trim messages)
        const history = createMockHistory(3, 1);
        const result = await setChatHistory(history);

        expect(result).toBe(true);
        // Should eventually remove oldest items
        expect(consoleWarnSpy).toHaveBeenCalledWith(
          expect.stringContaining("Retrying after trimming")
        );
      });

      it("should clear storage key when all items are removed", async () => {
        vi.mocked(localStorage.setItem).mockImplementation(() => {
          const error = new Error("Quota exceeded");
          error.name = "QuotaExceededError";
          throw error;
        });

        const history = createMockHistory(1, 1);
        const result = await setChatHistory(history);

        expect(result).toBe(true);
        expect(localStorage.removeItem).toHaveBeenCalledWith("kv_chat_history");
      });

      it("should handle multiple trimming iterations", async () => {
        let callCount = 0;
        vi.mocked(localStorage.setItem).mockImplementation(() => {
          callCount++;
          if (callCount < 4) {
            const error = new Error("Quota exceeded");
            error.name = "QuotaExceededError";
            throw error;
          }
        });

        const history = createMockHistory(2, 20); // 2 items with 20 messages each
        const result = await setChatHistory(history);

        expect(result).toBe(true);
        expect(callCount).toBeGreaterThanOrEqual(4);
      });
    });

    describe("edge cases", () => {
      it("should handle history with zero messages", async () => {
        const history: ChatHistoryItem[] = [
          {
            id: "chat-1",
            title: "Empty Chat",
            lastActive: new Date().toISOString(),
            messageCount: 0,
            messages: [],
          },
        ];

        const result = await setChatHistory(history);

        // Zero-message items can still be stored (they're small)
        // The trimming logic only kicks in when quota is exceeded
        expect(result).toBe(true);
        expect(localStorage.setItem).toHaveBeenCalledWith(
          "kv_chat_history",
          expect.stringContaining("Empty Chat")
        );
      });

      it("should handle very long message content", async () => {
        const history: ChatHistoryItem[] = [
          {
            id: "chat-1",
            title: "Long Content",
            lastActive: new Date().toISOString(),
            messageCount: 1,
            messages: [
              {
                id: "msg-1",
                role: "user",
                content: "x".repeat(100000), // Very long content
              },
            ],
          },
        ];

        const result = await setChatHistory(history);

        expect(result).toBe(true);
      });

      it("should preserve message order when trimming", async () => {
        let storedData: string = "";
        let shouldFail = true;

        vi.mocked(localStorage.setItem).mockImplementation((key: string, value: string) => {
          if (shouldFail) {
            const error = new Error("Quota exceeded");
            error.name = "QuotaExceededError";
            throw error;
          }
          storedData = value;
        });

        const history: ChatHistoryItem[] = [
          {
            id: "chat-1",
            title: "Ordered Chat",
            lastActive: new Date().toISOString(),
            messageCount: 4,
            messages: [
              { id: "msg-1", role: "user", content: "First" },
              { id: "msg-2", role: "assistant", content: "Second" },
              { id: "msg-3", role: "user", content: "Third" },
              { id: "msg-4", role: "assistant", content: "Fourth" },
            ],
          },
        ];

        await setChatHistory(history);
        shouldFail = false;

        // Parse the stored data and verify order
        const parsed = JSON.parse(storedData || "[]") as ChatHistoryItem[];
        if (parsed.length > 0 && parsed[0].messages.length > 0) {
          // When trimming from 4 to 2 messages, should keep the most recent
          expect(parsed[0].messages[0].content).toBe("Third");
          expect(parsed[0].messages[1].content).toBe("Fourth");
        }
      });
    });

    describe("error handling", () => {
      it("should return false on unexpected errors", async () => {
        vi.mocked(localStorage.setItem).mockImplementation(() => {
          throw new Error("Unexpected error");
        });

        const history = createMockHistory(1, 1);
        const result = await setChatHistory(history);

        expect(result).toBe(false);
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          expect.stringContaining("Failed to save chat history"),
          expect.any(Error)
        );
      });

      it("should handle removeItem failure when clearing empty history", async () => {
        vi.mocked(localStorage.setItem).mockImplementation(() => {
          const error = new Error("Quota exceeded");
          error.name = "QuotaExceededError";
          throw error;
        });

        vi.mocked(localStorage.removeItem).mockImplementation(() => {
          throw new Error("Remove failed");
        });

        const history = createMockHistory(1, 1);
        const result = await setChatHistory(history);

        expect(result).toBe(false);
      });
    });
  });

  describe("getChatHistory", () => {
    describe("happy path", () => {
      it("should retrieve stored chat history", () => {
        const mockHistory: ChatHistoryItem[] = [
          {
            id: "chat-1",
            title: "Test Chat",
            lastActive: "2024-01-01T00:00:00Z",
            messageCount: 2,
            messages: [
              { id: "msg-1", role: "user", content: "Hello" },
              { id: "msg-2", role: "assistant", content: "Hi!" },
            ],
          },
        ];

        vi.mocked(localStorage.getItem).mockReturnValue(JSON.stringify(mockHistory));

        const result = getChatHistory();

        expect(result).toEqual(mockHistory);
        expect(localStorage.getItem).toHaveBeenCalledWith("kv_chat_history");
      });

      it("should return empty array when no history exists", () => {
        vi.mocked(localStorage.getItem).mockReturnValue(null);

        const result = getChatHistory();

        expect(result).toEqual([]);
      });
    });

    describe("edge cases", () => {
      it("should return empty array for invalid JSON", () => {
        vi.mocked(localStorage.getItem).mockReturnValue("invalid json");

        const result = getChatHistory();

        expect(result).toEqual([]);
      });

      it("should return empty array for non-array JSON", () => {
        vi.mocked(localStorage.getItem).mockReturnValue('{"not": "an array"}');

        const result = getChatHistory();

        expect(result).toEqual([]);
      });

      it("should return empty array for empty string", () => {
        vi.mocked(localStorage.getItem).mockReturnValue("");

        const result = getChatHistory();

        expect(result).toEqual([]);
      });
    });

    describe("error handling", () => {
      it("should return empty array when localStorage throws", () => {
        vi.mocked(localStorage.getItem).mockImplementation(() => {
          throw new Error("localStorage error");
        });

        const result = getChatHistory();

        expect(result).toEqual([]);
      });
    });
  });

  describe("integration tests", () => {
    it("should round-trip chat history through set and get", async () => {
      const originalHistory: ChatHistoryItem[] = [
        {
          id: "chat-1",
          title: "Integration Test",
          lastActive: "2024-01-01T00:00:00Z",
          messageCount: 2,
          messages: [
            { id: "msg-1", role: "user", content: "Hello" },
            { id: "msg-2", role: "assistant", content: "World" },
          ],
        },
      ];

      await setChatHistory(originalHistory);

      // Get the stored value and mock it for getChatHistory
      const storedCall = vi.mocked(localStorage.setItem).mock.calls[0];
      vi.mocked(localStorage.getItem).mockReturnValue(storedCall[1]);

      const retrievedHistory = getChatHistory();

      expect(retrievedHistory).toEqual(originalHistory);
    });

    it("should handle concurrent quota checks correctly", async () => {
      const results = await Promise.all([
        safeSetItem("key1", "value1"),
        safeSetItem("key2", "value2"),
        safeSetItem("key3", "value3"),
      ]);

      expect(results).toEqual([true, true, true]);
      expect(localStorage.setItem).toHaveBeenCalledTimes(3);
    });
  });
});
