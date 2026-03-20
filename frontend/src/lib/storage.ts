/**
 * Storage utility module with quota enforcement for localStorage operations.
 * Provides safe storage methods that check available quota before writing.
 */

/**
 * Estimates the size of a string in bytes.
 * Assumes UTF-8 encoding where most characters are 1-2 bytes.
 * @param value - The string to measure
 * @returns Estimated size in bytes
 */
function estimateSize(value: string): number {
  // Use Blob for accurate byte size estimation
  return new Blob([value]).size;
}

/**
 * Gets the available storage quota using the Storage API.
 * Falls back to estimated values if the API is unavailable.
 * @returns Promise resolving to available bytes (or Infinity if unknown)
 */
async function getAvailableQuota(): Promise<number> {
  try {
    if (navigator.storage && navigator.storage.estimate) {
      const estimate = await navigator.storage.estimate();
      if (estimate.usage !== undefined && estimate.quota !== undefined) {
        return estimate.quota - estimate.usage;
      }
    }
  } catch {
    // Storage API not available or failed
  }
  // Fallback: assume we have some space available
  return Infinity;
}

/**
 * Safely stores a value in localStorage with quota checking.
 * Only writes if there's sufficient space available.
 *
 * @param key - The localStorage key to set
 * @param value - The string value to store
 * @returns Promise resolving to true on success, false if quota exceeded
 */
export async function safeSetItem(key: string, value: string): Promise<boolean> {
  try {
    const valueSize = estimateSize(value);
    const availableQuota = await getAvailableQuota();

    // Check if we have enough space (with some buffer for safety)
    const BUFFER_BYTES = 1024; // 1KB buffer
    if (availableQuota !== Infinity && valueSize + BUFFER_BYTES > availableQuota) {
      console.warn(
        `[storage] Quota exceeded: need ${valueSize} bytes, ` +
        `have ${availableQuota} bytes available (key: ${key})`
      );
      return false;
    }

    localStorage.setItem(key, value);
    return true;
  } catch (err) {
    // Handle QuotaExceededError specifically
    if (err instanceof Error && err.name === "QuotaExceededError") {
      console.warn(`[storage] Quota exceeded for key: ${key}`);
      return false;
    }
    // Re-throw other errors
    throw err;
  }
}

/**
 * Represents a single chat message in the history.
 */
export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  sources?: Array<{ id: string; filename: string; snippet?: string; score?: number }>;
}

/**
 * Represents a chat history item/session.
 */
export interface ChatHistoryItem {
  id: string;
  title: string;
  lastActive: string;
  messageCount: number;
  messages: ChatMessage[];
}

/**
 * Stores chat history with automatic quota enforcement and retry logic.
 * If quota is exceeded, trims old messages and retries until successful
 * or until history is empty.
 *
 * @param history - The chat history array to store
 * @returns Promise resolving to true on success, false if completely failed
 */
export async function setChatHistory(history: ChatHistoryItem[]): Promise<boolean> {
  const STORAGE_KEY = "kv_chat_history";

  // Try to serialize and store
  let currentHistory = history;

  while (currentHistory.length > 0) {
    try {
      const serialized = JSON.stringify(currentHistory);
      const success = await safeSetItem(STORAGE_KEY, serialized);

      if (success) {
        return true;
      }

      // Quota exceeded - trim oldest messages from each item
      let trimmed = false;
      const newHistory: ChatHistoryItem[] = [];

      for (const item of currentHistory) {
        if (item.messages.length > 1) {
          // Keep at least one message, trim the rest from the oldest
          const trimmedItem: ChatHistoryItem = {
            ...item,
            messages: item.messages.slice(-Math.max(1, Math.floor(item.messages.length / 2))),
            messageCount: Math.max(1, Math.floor(item.messages.length / 2)),
          };
          newHistory.push(trimmedItem);
          trimmed = true;
        } else if (item.messages.length === 1) {
          // Keep items with single messages
          newHistory.push(item);
        }
      }

      if (!trimmed) {
        // Can't trim further - remove oldest items entirely
        currentHistory = currentHistory.slice(1);
      } else {
        currentHistory = newHistory;
      }

      console.warn(
        `[storage] Retrying after trimming history: ${history.length} → ${currentHistory.length} items`
      );
    } catch (err) {
      console.error("[storage] Failed to save chat history:", err);
      return false;
    }
  }

  // If we get here with empty history, try to clear the key
  try {
    localStorage.removeItem(STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

/**
 * Retrieves chat history from localStorage.
 * @returns The stored chat history or empty array if not found/invalid
 */
export function getChatHistory(): ChatHistoryItem[] {
  try {
    const stored = localStorage.getItem("kv_chat_history");
    if (!stored) {
      return [];
    }
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed)) {
      return parsed as ChatHistoryItem[];
    }
    return [];
  } catch {
    return [];
  }
}
