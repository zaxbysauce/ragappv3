export type ChatMode = "instant" | "thinking";

export interface ChatModeInputs {
  /** Persisted user preference. ``null`` / ``undefined`` means "follow default". */
  stored: ChatMode | null | undefined;
  /** Backend-configured default mode. */
  defaultMode: ChatMode | null | undefined;
  thinkingHealthy: boolean;
  instantHealthy: boolean;
}

/**
 * Resolve which chat mode will actually run, applying health-based fallback.
 *
 * Must be the single source of truth for both the Composer's displayed
 * highlight and the request payload sent by useSendMessage so the user
 * never sees one mode while another is silently used.
 */
export function computeEffectiveChatMode(inputs: ChatModeInputs): ChatMode {
  const desired: ChatMode = inputs.stored ?? inputs.defaultMode ?? "thinking";
  if (desired === "instant" && !inputs.instantHealthy && inputs.thinkingHealthy) {
    return "thinking";
  }
  if (desired === "thinking" && !inputs.thinkingHealthy && inputs.instantHealthy) {
    return "instant";
  }
  return desired;
}
