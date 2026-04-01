import { useState, useCallback, useEffect, useRef } from "react";
import { toast } from "sonner";
import { useDebounce } from "./useDebounce";
import { searchMemories, listMemories, type MemoryResult } from "@/lib/api";

export interface UseMemorySearchReturn {
  memories: MemoryResult[];
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  loading: boolean;
  handleSearch: () => Promise<void>;
}

/** Manages memory search with debounced queries and abort-on-unmount cleanup. */
export function useMemorySearch(activeVaultId: number | null): UseMemorySearchReturn {
  const [memories, setMemories] = useState<MemoryResult[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery] = useDebounce(searchQuery, 300);
  const [loading, setLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleSearch = useCallback(async () => {
    // Cancel any pending request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setLoading(true);
    try {
      if (debouncedSearchQuery.trim()) {
        // Search mode — use POST /memories/search
        const response = await searchMemories(
          { query: debouncedSearchQuery, limit: 50 },
          abortController.signal,
          activeVaultId ?? undefined
        );
        if (!abortController.signal.aborted) {
          setMemories(response.results || []);
        }
      } else {
        // List mode — use GET /memories
        const response = await listMemories(activeVaultId ?? undefined);
        if (!abortController.signal.aborted) {
          setMemories(response.memories || []);
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      console.error("Failed to load memories:", err);
      toast.error(err instanceof Error ? err.message : "Failed to load memories");
    } finally {
      if (!abortController.signal.aborted) {
        setLoading(false);
      }
    }
  }, [debouncedSearchQuery, activeVaultId]);

  useEffect(() => {
    handleSearch();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [handleSearch]);

  return {
    memories,
    searchQuery,
    setSearchQuery,
    loading,
    handleSearch,
  };
}

// Re-export MemoryResult type for convenience
export type { MemoryResult };
