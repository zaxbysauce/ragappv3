import { useState, useEffect, useCallback, useRef } from "react";
import apiClient, { type HealthResponse } from "@/lib/api";
import type { HealthStatus } from "@/types/health";

interface UseHealthCheckOptions {
  pollInterval?: number;
}

/** Polls the backend health endpoint and returns service availability status. */
export function useHealthCheck(options?: UseHealthCheckOptions): HealthStatus {
  const [health, setHealth] = useState<HealthStatus>({
    backend: false,
    embeddings: false,
    chat: false,
    loading: true,
    lastChecked: null,
  });

  const isFirstCheck = useRef(true);

  const checkHealth = useCallback(async () => {
    try {
      // First check includes deep model probing; subsequent polls are lightweight
      const params = isFirstCheck.current ? { deep: true } : {};
      isFirstCheck.current = false;

      const response = await apiClient.get<HealthResponse>("/health", { params });
      const services = response.data.services;

      setHealth({
        backend: services?.backend ?? response.data.status === "ok",
        embeddings: services?.embeddings ?? false,
        chat: services?.chat ?? false,
        loading: false,
        lastChecked: new Date(),
      });
    } catch {
      setHealth({
        backend: false,
        embeddings: false,
        chat: false,
        loading: false,
        lastChecked: new Date(),
      });
    }
  }, []);

  useEffect(() => {
    checkHealth();

    if (options?.pollInterval) {
      const interval = setInterval(checkHealth, options.pollInterval);
      return () => clearInterval(interval);
    }
  }, [checkHealth, options?.pollInterval]);

  return health;
}
