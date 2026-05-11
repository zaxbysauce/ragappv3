import { create } from "zustand";
import { getLlmModeHealth } from "@/lib/api";

interface LlmHealthState {
  thinking: boolean;
  instant: boolean;
  lastCheckedAt: number | null;
  refreshing: boolean;
  refresh: () => Promise<void>;
}

/**
 * Tracks live availability of both LLM backends. The composer reads this to
 * gate the Instant mode toggle. Fails closed: any error sets both backends to
 * ``false`` so the UI shows them as unavailable rather than silently routing
 * to a dead endpoint.
 */
export const useLlmHealthStore = create<LlmHealthState>((set, get) => ({
  thinking: false,
  instant: false,
  lastCheckedAt: null,
  refreshing: false,
  refresh: async () => {
    if (get().refreshing) return;
    set({ refreshing: true });
    try {
      const status = await getLlmModeHealth();
      set({
        thinking: !!status.thinking,
        instant: !!status.instant,
        lastCheckedAt: Date.now(),
        refreshing: false,
      });
    } catch {
      // Fail closed: mark both backends down so the toggle disables.
      set({
        thinking: false,
        instant: false,
        lastCheckedAt: Date.now(),
        refreshing: false,
      });
    }
  },
}));
