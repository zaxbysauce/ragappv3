import { create } from "zustand";
import { persist } from "zustand/middleware";
import axios from "axios";
import { setJwtAccessToken, getJwtAccessToken } from "@/lib/api";

interface User {
  id: number;
  username: string;
  full_name: string;
  role: "superadmin" | "admin" | "member" | "viewer";
  is_active: boolean;
}

interface LoginResponse {
  access_token: string;
  user?: User;
}

interface RegisterResponse {
  access_token: string;
  user: User;
}

interface AuthState {
  // State
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  needsSetup: boolean | null;
  authMode: "jwt" | "apikey" | "unknown";

  // Actions
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<string | null>;
  fetchMe: () => Promise<void>;
  checkSetupStatus: () => Promise<void>;
  setAuthMode: (mode: "jwt" | "apikey") => void;
  updateProfile: (data: { full_name?: string; password?: string }) => Promise<void>;
  init: () => Promise<void>;

  // Internal
  _setLoading: (loading: boolean) => void;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

// Create a separate axios instance for auth calls to avoid interceptor loops
const authClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true, // Required for httpOnly refresh cookie
});

/**
 * Fetch a CSRF token from the backend and attach it to subsequent requests.
 * The backend sets the token as a cookie; we read it and echo it back via
 * the X-CSRF-Token header on every mutating request.
 */
let csrfToken: string | null = null;
let csrfFetchPromise: Promise<string> | null = null;

async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  if (!csrfFetchPromise) {
    csrfFetchPromise = authClient
      .get<{ csrf_token: string }>("/csrf-token")
      .then((resp) => {
        csrfToken = resp.data.csrf_token;
        return csrfToken;
      })
      .finally(() => {
        csrfFetchPromise = null;
      });
  }
  return csrfFetchPromise;
}

// Attach CSRF token to all mutating requests
authClient.interceptors.request.use(async (config) => {
  if (config.method && ["post", "put", "patch", "delete"].includes(config.method.toLowerCase())) {
    const token = await ensureCsrfToken();
    config.headers["X-CSRF-Token"] = token;
  }
  return config;
});

// If a 403 CSRF error occurs, clear the stale token so it gets refreshed on retry
authClient.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    if (error.response?.status === 403) {
      csrfToken = null; // force refresh on next request
    }
    return Promise.reject(error);
  }
);

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isLoading: false,
      needsSetup: null as boolean | null,
      authMode: "unknown",

      _setLoading: (loading: boolean) => set({ isLoading: loading }),

      setAuthMode: (mode: "jwt" | "apikey") => set({ authMode: mode }),

      init: async () => {
        const state = get();
        set({ isLoading: true });
        try {
          // Check if we have an existing session by calling /auth/me
          if (state.accessToken) {
            await get().fetchMe();
            set({ authMode: "jwt", isAuthenticated: true, isLoading: false });
            return;
          }
        } catch {
          // Access token invalid or expired — try to refresh via httpOnly cookie
          // before giving up and forcing the user to log in again.
          try {
            const newToken = await get().refreshToken();
            if (newToken) {
              await get().fetchMe();
              set({ authMode: "jwt", isAuthenticated: true, isLoading: false });
              return;
            }
          } catch {
            // Refresh also failed — fall through to clear state
          }
          // Both access token and refresh cookie are invalid
          set({
            accessToken: null,
            user: null,
            isAuthenticated: false,
          });
          setJwtAccessToken(null);
        }
        try {
          // Check setup status
          await get().checkSetupStatus();
        } catch {
          // Backend unreachable — auth mode unknown
        }
        // Check if API key auth is active
        const apiKey = localStorage.getItem("kv_api_key");
        if (apiKey) {
          set({ authMode: "apikey", isAuthenticated: true, isLoading: false });
        } else {
          set({ authMode: "jwt", isLoading: false });
        }
      },

      checkSetupStatus: async () => {
        try {
          const response = await authClient.get<{ needs_setup: boolean }>(
            "/auth/setup-status"
          );
          set({ needsSetup: response.data.needs_setup });
        } catch (error) {
          console.error("Failed to check setup status:", error);
          set({ needsSetup: false });
        }
      },

      login: async (username: string, password: string) => {
        get()._setLoading(true);
        try {
          const response = await authClient.post<LoginResponse>("/auth/login", {
            username,
            password,
          });

          const { access_token, user } = response.data;

          // Update store state
          set({
            accessToken: access_token,
            user: user || null,
            isAuthenticated: true,
            authMode: "jwt",
          });

          // Sync with apiClient
          setJwtAccessToken(access_token);

          // If user wasn't included in login response, fetch it
          if (!user) {
            await get().fetchMe();
          }
        } finally {
          get()._setLoading(false);
        }
      },

      register: async (username: string, password: string, fullName?: string) => {
        get()._setLoading(true);
        try {
          const response = await authClient.post<RegisterResponse>("/auth/register", {
            username,
            password,
            full_name: fullName,
          });

          // Backend returns flat response, construct User object manually
          const { access_token, id, username: uname, full_name, role, is_active } = response.data as any;
          const user: User = { id, username: uname, full_name, role, is_active };

          // Update store state
          set({
            accessToken: access_token,
            user: user,
            isAuthenticated: true,
            authMode: "jwt",
            needsSetup: false,
          });

          // Sync with apiClient
          setJwtAccessToken(access_token);
        } finally {
          get()._setLoading(false);
        }
      },

      logout: async () => {
        get()._setLoading(true);
        try {
          // Call logout endpoint to clear httpOnly cookie
          await authClient.post("/auth/logout", {}, { withCredentials: true });
        } catch (error) {
          console.error("Logout request failed:", error);
          // Continue with local cleanup even if server logout fails
        } finally {
          // Clear all auth state
          set({
            user: null,
            accessToken: null,
            isAuthenticated: false,
          });
          setJwtAccessToken(null);
          get()._setLoading(false);
        }
      },

      refreshToken: async (): Promise<string | null> => {
        try {
          const response = await authClient.post<{ access_token: string }>(
            "/auth/refresh",
            {},
            { withCredentials: true }
          );

          const { access_token } = response.data;

          // Update store and apiClient
          set({ accessToken: access_token });
          setJwtAccessToken(access_token);

          return access_token;
        } catch (error) {
          console.error("Token refresh failed:", error);
          // Clear auth state on refresh failure
          set({
            user: null,
            accessToken: null,
            isAuthenticated: false,
          });
          setJwtAccessToken(null);
          return null;
        }
      },

      fetchMe: async () => {
        try {
          const token = get().accessToken || getJwtAccessToken();
          if (!token) {
            throw new Error("No access token available");
          }

          const response = await authClient.get<User>("/auth/me", {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          set({
            user: response.data,
            isAuthenticated: true,
          });
        } catch (error) {
          console.error("Failed to fetch user:", error);
          // Don't clear auth here - let the caller decide (e.g., redirect to login)
          throw error;
        }
      },

      updateProfile: async (data: { full_name?: string; password?: string }) => {
        get()._setLoading(true);
        try {
          const token = get().accessToken || getJwtAccessToken();
          if (!token) {
            throw new Error("No access token available");
          }

          const response = await authClient.patch<User>("/auth/me", data, {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          set({ user: response.data });
        } finally {
          get()._setLoading(false);
        }
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        authMode: state.authMode,
        needsSetup: state.needsSetup,
      }),
    }
  )
);

// Auto-sync: when store hydrates from persist, sync token to api.ts
const initialState = useAuthStore.getState();
if (initialState.accessToken) {
  setJwtAccessToken(initialState.accessToken);
}

// Subscribe to token changes to keep api.ts in sync
useAuthStore.subscribe((state, prevState) => {
  if (state.accessToken !== prevState.accessToken) {
    setJwtAccessToken(state.accessToken);
  }
});
