import axios from "axios";
import { setChatHistory as storageSetChatHistory, getChatHistory as storageGetChatHistory } from "./storage";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

// Module-level JWT token holder - persisted via useAuthStore persist middleware
let _jwtAccessToken: string | null = null;

export function setJwtAccessToken(token: string | null): void {
  _jwtAccessToken = token;
}

export function getJwtAccessToken(): string | null {
  return _jwtAccessToken;
}

// Read CSRF token from the non-httpOnly cookie set by the server
function getCsrfCookie(): string | null {
  const match = document.cookie
    .split('; ')
    .find(row => row.startsWith('X-CSRF-Token='));
  // Use split with limit=2 so token values containing '=' (base64 padding) are preserved
  return match ? decodeURIComponent(match.split('=', 2)[1]) : null;
}

// Singleton refresh promise — ensures only one /auth/refresh call is in flight
// at a time. Concurrent 401s share the same promise so the refresh cookie is
// not rotated twice (which would invalidate the second caller's session).
let _refreshInFlight: Promise<string | null> | null = null;

// Standalone refresh function to avoid circular dependencies
async function refreshAccessToken(): Promise<string | null> {
  if (_refreshInFlight) {
    return _refreshInFlight;
  }
  _refreshInFlight = _doRefresh().finally(() => {
    _refreshInFlight = null;
  });
  return _refreshInFlight;
}

async function _doRefresh(): Promise<string | null> {
  try {
    // The /auth/refresh endpoint requires the CSRF token.
    // Read it from the non-httpOnly cookie; if missing, fetch a fresh one.
    let csrfToken = getCsrfCookie();
    if (!csrfToken) {
      try {
        const csrfResp = await fetch(`${API_BASE_URL}/csrf-token`, { credentials: "include" });
        if (csrfResp.ok) {
          const csrfData = await csrfResp.json();
          csrfToken = csrfData.csrf_token ?? null;
        }
      } catch {
        // proceed without CSRF — server will reject if required
      }
    }

    const headers: Record<string, string> = {};
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }

    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include", // Send httpOnly cookie with refresh token
      headers,
    });
    if (!response.ok) return null;
    const data = await response.json();
    _jwtAccessToken = data.access_token;
    return data.access_token;
  } catch {
    return null;
  }
}

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach authentication token (JWT takes precedence over API key)
apiClient.interceptors.request.use((config) => {
  // JWT takes precedence over API key
  if (_jwtAccessToken) {
    config.headers.Authorization = `Bearer ${_jwtAccessToken}`;
    return config;
  }
  const apiKey = localStorage.getItem("kv_api_key");
  if (apiKey) {
    config.headers.Authorization = `Bearer ${apiKey}`;
  }
  return config;
});

// Parse JWT token to extract expiry timestamp (exp claim)
function getTokenExpiry(token: string): number | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload.exp ? payload.exp * 1000 : null; // Convert to milliseconds
  } catch {
    return null;
  }
}

// Check if token is expired or close to expiring (within 1 minute)
function isTokenNearExpiry(token: string, bufferMs: number = 60000): boolean {
  const expiry = getTokenExpiry(token);
  if (!expiry) return false;
  return Date.now() + bufferMs >= expiry;
}

// Normalize error responses
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Preserve AbortError for cancellation handling
    if (error.name === "AbortError" || error.code === "ERR_CANCELED") {
      return Promise.reject(error);
    }

    // Handle 401 Unauthorized - attempt silent refresh for JWT, or clear API key
    if (error.response?.status === 401) {
      // JWT auth: attempt silent token refresh before redirecting
      if (_jwtAccessToken) {
        // Use a flag to prevent infinite refresh loops
        if (!error.config._retry) {
          error.config._retry = true;
          try {
            const newToken = await refreshAccessToken();
            if (newToken) {
              error.config.headers.Authorization = `Bearer ${newToken}`;
              return apiClient(error.config);
            }
          } catch {
            // Refresh failed, fall through to logout
          }
        }
        // Clear JWT auth
        _jwtAccessToken = null;
        window.dispatchEvent(new CustomEvent("auth:unauthorized"));
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
      } else {
        // API key auth: clear the key and redirect
        localStorage.removeItem("kv_api_key");
        // Dispatch custom event that AuthProvider can listen to
        window.dispatchEvent(new CustomEvent("auth:unauthorized"));
        // Also try to redirect using router if available
        if (window.history && window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
      }
    }

    // Extract the most useful error message
    let message = "An unexpected error occurred";
    
    if (error.response) {
      // Server responded with an error status
      const data = error.response.data;
      message = data?.detail || data?.message || data?.error || error.response.statusText || message;
    } else if (error.request) {
      // Request was made but no response received
      message = "Unable to reach the server. Please check your connection.";
    } else {
      // Something else happened
      message = error.message || message;
    }

    // Create a normalized error with the extracted message
    const normalizedError = new Error(message);
    normalizedError.name = error.name || "APIError";
    // Preserve the original response for status code checking
    (normalizedError as any).status = error.response?.status;
    (normalizedError as any).originalError = error;
    
    return Promise.reject(normalizedError);
  }
);

export interface HealthResponse {
  status: string;
  version?: string;
  timestamp?: string;
  services?: {
    backend: boolean;
    embeddings: boolean;
    chat: boolean;
  };
}

export interface ConnectionCheck {
  url: string;
  status: number | null;
  ok: boolean;
  error?: string;
}

export interface ConnectionTestResult {
  embeddings: ConnectionCheck;
  chat: ConnectionCheck;
}

export interface SettingsResponse {
  // Server config
  port: number;
  data_dir: string;

  // Ollama config
  ollama_embedding_url: string;
  ollama_chat_url: string;

  // Model config
  embedding_model: string;
  chat_model: string;

  // Document processing (character-based)
  chunk_size_chars: number;
  chunk_overlap_chars: number;
  retrieval_top_k: number;

  // RAG config
  max_distance_threshold: number;
  retrieval_window: number;
  vector_metric: string;

  // Embedding prefixes
  embedding_doc_prefix: string;
  embedding_query_prefix: string;

  // Feature flags
  maintenance_mode: boolean;
  auto_scan_enabled: boolean;
  auto_scan_interval_minutes: number;
  enable_model_validation: boolean;

  // Embedding batch size
  embedding_batch_size: number;

  // Retrieval settings
  reranking_enabled?: boolean;
  reranker_url?: string;
  reranker_model?: string;
  initial_retrieval_top_k?: number;
  reranker_top_n?: number;
  hybrid_search_enabled?: boolean;
  hybrid_alpha?: number;

  // Limits
  max_file_size_mb: number;
  allowed_extensions: string[];

  // CORS
  backend_cors_origins: string[];
}

export interface UpdateSettingsRequest {
  chunk_size_chars?: number;
  chunk_overlap_chars?: number;
  retrieval_top_k?: number;
  auto_scan_enabled?: boolean;
  auto_scan_interval_minutes?: number;
  max_distance_threshold?: number;
  retrieval_window?: number;
  vector_metric?: string;
  embedding_doc_prefix?: string;
  embedding_query_prefix?: string;
  embedding_batch_size?: number;
  // Retrieval settings
  reranking_enabled?: boolean;
  reranker_url?: string;
  reranker_model?: string;
  initial_retrieval_top_k?: number;
  reranker_top_n?: number;
  hybrid_search_enabled?: boolean;
  hybrid_alpha?: number;
  // Model connection settings
  ollama_embedding_url?: string;
  ollama_chat_url?: string;
  embedding_model?: string;
  chat_model?: string;
}

export interface SearchMemoriesRequest {
  query: string;
  limit?: number;
  filter?: Record<string, unknown>;
}

export interface MemoryResult {
  id: string;
  content: string;
  metadata?: Record<string, unknown>;
  score?: number;
}

export interface AddMemoryRequest {
  content: string;
  category?: string;
  tags?: string[];
  source?: string;
}

export interface AddMemoryResponse {
  id: string;
  status: string;
}

export interface SearchMemoriesResponse {
  results: MemoryResult[];
  total: number;
}

export interface Document {
  id: string;
  filename: string;
  content_type?: string;
  size?: number;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface ListDocumentsResponse {
  documents: Document[];
  total: number;
}

export interface UploadDocumentResponse {
  id: string;
  filename: string;
  status: string;
}

export interface DocumentStatsResponse {
  total_documents: number;
  total_chunks: number;
  total_size_bytes: number;
  documents_by_status: Record<string, number>;
}

export interface ScanDocumentsResponse {
  scanned: number;
  added: number;
  errors: string[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface Source {
  id: string;
  file_id?: string;
  filename: string;
  section?: string;
  source_label?: string;
  evidence_type?: "primary" | "supporting";
  snippet?: string;
  score?: number;
  score_type?: "distance" | "rerank" | "rrf";
}

export interface ChatStreamCallbacks {
  onMessage: (chunk: string) => void;
  onSources?: (sources: Source[]) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

export interface ChatHistoryItem {
  id: string;
  title: string;
  lastActive: string;
  messageCount: number;
  messages: Array<{ id: string; role: string; content: string; sources?: Source[] }>;
}

export interface ChatSession {
  id: number;
  vault_id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface ChatSessionMessage {
  id: number;
  role: string;
  content: string;
  sources: Source[] | null;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatSessionMessage[];
}

export interface CreateSessionRequest {
  title?: string;
  vault_id?: number;
}

export interface AddMessageRequest {
  role: string;
  content: string;
  sources?: Source[];
}

export interface Vault {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  file_count: number;
  memory_count: number;
  session_count: number;
}

export interface VaultListResponse {
  vaults: Vault[];
}

export interface VaultCreateRequest {
  name: string;
  description?: string;
}

export interface VaultUpdateRequest {
  name?: string;
  description?: string;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>("/health");
  return response.data;
}

export async function getSettings(): Promise<SettingsResponse> {
  const response = await apiClient.get<SettingsResponse>("/settings");
  return response.data;
}

export async function updateSettings(
  request: UpdateSettingsRequest
): Promise<SettingsResponse> {
  const response = await apiClient.put<SettingsResponse>("/settings", request);
  return response.data;
}

export async function testConnections(): Promise<ConnectionTestResult> {
  const response = await apiClient.get<ConnectionTestResult>("/settings/connection");
  return response.data;
}

export async function listVaults(): Promise<VaultListResponse> {
  const response = await apiClient.get<VaultListResponse>("/vaults");
  return response.data;
}

export async function getVault(id: number): Promise<Vault> {
  const response = await apiClient.get<Vault>(`/vaults/${id}`);
  return response.data;
}

export async function createVault(request: VaultCreateRequest): Promise<Vault> {
  const response = await apiClient.post<Vault>("/vaults", request);
  return response.data;
}

export async function updateVault(id: number, request: VaultUpdateRequest): Promise<Vault> {
  const response = await apiClient.put<Vault>(`/vaults/${id}`, request);
  return response.data;
}

export async function deleteVault(id: number): Promise<void> {
  await apiClient.delete(`/vaults/${id}`);
}

export async function searchMemories(
  request: SearchMemoriesRequest,
  signal?: AbortSignal,
  vaultId?: number
): Promise<SearchMemoriesResponse> {
  const body = { ...request, ...(vaultId != null && { vault_id: vaultId }) };
  const response = await apiClient.post<SearchMemoriesResponse>(
    "/memories/search",
    body,
    { signal }
  );
  return response.data;
}

export async function addMemory(
  request: AddMemoryRequest,
  vaultId?: number
): Promise<AddMemoryResponse> {
  // Ensure tags is always an array, never undefined
  const payload = {
    ...request,
    tags: request.tags ?? [],
    ...(vaultId != null && { vault_id: vaultId }),
  };
  const response = await apiClient.post<AddMemoryResponse>("/memories", payload);
  return response.data;
}

export async function deleteMemory(id: string): Promise<void> {
  await apiClient.delete(`/memories/${id}`);
}

export async function listMemories(vaultId?: number): Promise<{ memories: MemoryResult[] }> {
  const response = await apiClient.get<{ memories: MemoryResult[] }>(
    "/memories",
    vaultId != null ? { params: { vault_id: vaultId } } : undefined
  );
  return response.data;
}

export async function listDocuments(vaultId?: number): Promise<ListDocumentsResponse> {
  const response = await apiClient.get<ListDocumentsResponse>("/documents", vaultId != null ? { params: { vault_id: vaultId } } : undefined);
  return response.data;
}

export async function uploadDocument(
  file: File,
  onProgress?: (progress: number) => void,
  vaultId?: number
): Promise<UploadDocumentResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post<UploadDocumentResponse>(
    "/documents",
    formData,
    {
      headers: { "Content-Type": "" },
      ...(vaultId != null && { params: { vault_id: vaultId } }),
      onUploadProgress: (progressEvent) => {
        if (onProgress) {
          if (progressEvent.total) {
            const progress = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            onProgress(progress);
          } else {
            // Total unknown - report 0 for indeterminate progress
            onProgress(0);
          }
        }
      },
    }
  );
  return response.data;
}

export async function scanDocuments(vaultId?: number): Promise<ScanDocumentsResponse> {
  const response = await apiClient.post<ScanDocumentsResponse>(
    "/documents/scan",
    undefined,
    vaultId != null ? { params: { vault_id: vaultId } } : undefined
  );
  return response.data;
}

export async function deleteDocument(fileId: string): Promise<void> {
  await apiClient.delete(`/documents/${fileId}`);
}

export async function deleteDocuments(fileIds: string[]): Promise<{ deleted_count: number, failed_ids: string[] }> {
  const response = await apiClient.post<{ deleted_count: number, failed_ids: string[] }>("/documents/batch", { file_ids: fileIds });
  return response.data;
}

export async function deleteAllDocumentsInVault(vaultId: number): Promise<{ deleted_count: number, vault_id: number }> {
  const response = await apiClient.delete<{ deleted_count: number, vault_id: number }>(`/documents/vault/${vaultId}/all`);
  return response.data;
}

export async function getDocumentStats(vaultId?: number): Promise<DocumentStatsResponse> {
  const response = await apiClient.get<DocumentStatsResponse>("/documents/stats", vaultId != null ? { params: { vault_id: vaultId } } : undefined);
  return response.data;
}

export function chatStream(
  messages: ChatMessage[],
  callbacks: ChatStreamCallbacks,
  vaultId?: number
): () => void {
  const abortController = new AbortController();

  const startStream = async () => {
    try {
      // Pre-stream token refresh check: if JWT is close to expiring, refresh it first
      if (_jwtAccessToken && isTokenNearExpiry(_jwtAccessToken)) {
        const refreshedToken = await refreshAccessToken();
        if (!refreshedToken) {
          // Refresh failed - dispatch auth error and abort
          window.dispatchEvent(new CustomEvent("auth:unauthorized"));
          callbacks.onError?.(new Error("Session expired. Please log in again."));
          return;
        }
      }

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      // JWT takes precedence over API key
      if (_jwtAccessToken) {
        headers["Authorization"] = `Bearer ${_jwtAccessToken}`;
      } else {
        const apiKey = localStorage.getItem("kv_api_key");
        if (apiKey) {
          headers["Authorization"] = `Bearer ${apiKey}`;
        }
      }

      const response = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ messages, ...(vaultId != null && { vault_id: vaultId }) }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Response body is not readable");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const data = trimmed.slice(6);
            if (data === "[DONE]") {
              callbacks.onComplete?.();
              return;
            }
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'error') {
                callbacks.onError?.(new Error(parsed.message || 'Chat stream error'));
                return;
              }
              if (parsed.content) {
                callbacks.onMessage(parsed.content);
              }
              if (parsed.sources) {
                // Inject score_type from done event into each source
                const scoreType = (parsed as any).score_type as Source["score_type"];
                const enrichedSources = scoreType
                  ? parsed.sources.map((s: Source) => ({ ...s, score_type: scoreType }))
                  : parsed.sources;
                callbacks.onSources?.(enrichedSources);
              }
            } catch {
              callbacks.onMessage(data);
            }
          }
        }
      }

      callbacks.onComplete?.();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }
      callbacks.onError?.(
        error instanceof Error ? error : new Error(String(error))
      );
    }
  };

  startStream();

  return () => {
    abortController.abort();
  };
}

export function getChatHistory(): ChatHistoryItem[] {
  return storageGetChatHistory();
}

export async function saveChatHistory(history: ChatHistoryItem[]): Promise<void> {
  try {
    const success = await storageSetChatHistory(history);
    if (!success) {
      console.warn("Failed to save chat history: quota exceeded even after trimming");
    }
  } catch (err) {
    console.error("Failed to save chat history:", err);
  }
}

export async function listChatSessions(vaultId?: number): Promise<{ sessions: ChatSession[] }> {
  const response = await apiClient.get<{ sessions: ChatSession[] }>(
    "/chat/sessions",
    vaultId != null ? { params: { vault_id: vaultId } } : undefined
  );
  return response.data;
}

export async function getChatSession(sessionId: number): Promise<ChatSessionDetail> {
  const response = await apiClient.get<ChatSessionDetail>(`/chat/sessions/${sessionId}`);
  return response.data;
}

export async function createChatSession(request: CreateSessionRequest): Promise<ChatSession> {
  const response = await apiClient.post<ChatSession>("/chat/sessions", request);
  return response.data;
}

export async function addChatMessage(sessionId: number, request: AddMessageRequest): Promise<ChatSessionMessage> {
  const response = await apiClient.post<ChatSessionMessage>(`/chat/sessions/${sessionId}/messages`, request);
  return response.data;
}

export async function updateChatSession(sessionId: number, title: string): Promise<ChatSession> {
  const response = await apiClient.put<ChatSession>(`/chat/sessions/${sessionId}`, { title });
  return response.data;
}

export async function deleteChatSession(sessionId: number): Promise<void> {
  await apiClient.delete(`/chat/sessions/${sessionId}`);
}

// ============================================================================
// Session Interfaces and Functions
// ============================================================================

export interface Session {
  id: string;
  user_id: number;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface SessionListResponse {
  sessions: Session[];
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const request: ChangePasswordRequest = {
    current_password: currentPassword,
    new_password: newPassword,
  };
  await apiClient.post("/auth/change-password", request);
}

export async function listSessions(): Promise<SessionListResponse> {
  const response = await apiClient.get<SessionListResponse>("/auth/sessions");
  return response.data;
}

export async function revokeSession(sessionId: number): Promise<void> {
  await apiClient.delete(`/auth/sessions/${sessionId}`);
}

export async function revokeAllSessions(): Promise<{ access_token: string; token_type: string; expires_in: number }> {
  const response = await apiClient.delete<{ access_token: string; token_type: string; expires_in: number }>("/auth/sessions");
  return response.data;
}

// ============================================================================
// Group Interfaces and Functions
// ============================================================================

export interface Group {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  org_id: number;
  organization_name: string;
}

export interface GroupCreateRequest {
  name: string;
  description: string;
}

export interface GroupUpdateRequest {
  name: string;
  description: string;
}

export interface GroupListResponse {
  groups: Group[];
  total: number;
  page: number;
  per_page: number;
}

export async function listGroups(
  page?: number,
  perPage?: number,
  search?: string
): Promise<GroupListResponse> {
  const params: Record<string, string | number> = {};
  if (page !== undefined) params.page = page;
  if (perPage !== undefined) params.per_page = perPage;
  if (search !== undefined) params.search = search;

  const response = await apiClient.get<GroupListResponse>("/groups", { params });
  return response.data;
}

export async function createGroup(name: string, description: string): Promise<Group> {
  const request: GroupCreateRequest = { name, description };
  const response = await apiClient.post<Group>("/groups", request);
  return response.data;
}

export async function updateGroup(
  groupId: number,
  name: string,
  description: string
): Promise<Group> {
  const request: GroupUpdateRequest = { name, description };
  const response = await apiClient.put<Group>(`/groups/${groupId}`, request);
  return response.data;
}

export async function deleteGroup(groupId: number): Promise<void> {
  await apiClient.delete(`/groups/${groupId}`);
}

export interface GroupMember {
  id: number;
  username: string;
  full_name: string | null;
}

export async function getGroupMembers(groupId: number): Promise<GroupMember[]> {
  const response = await apiClient.get<GroupMember[]>(`/groups/${groupId}/members`);
  return response.data;
}

export async function updateGroupMembers(groupId: number, userIds: number[]): Promise<void> {
  await apiClient.put(`/groups/${groupId}/members`, { user_ids: userIds });
}

export async function getGroupVaults(groupId: number): Promise<GroupVault[]> {
  const response = await apiClient.get<GroupVault[]>(`/groups/${groupId}/vaults`);
  return response.data;
}

export async function updateGroupVaults(groupId: number, vaultIds: number[]): Promise<void> {
  await apiClient.put(`/groups/${groupId}/vaults`, { vault_ids: vaultIds });
}

// ============================================================================
// User Interfaces and Functions
// ============================================================================

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserListItem {
  id: number;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
}

export async function listAllUsers(): Promise<UserListItem[]> {
  const response = await apiClient.get<{ users: UserListItem[] }>("/users");
  return response.data.users;
}

export async function getGroupVaultIds(groupId: number): Promise<number[]> {
  const response = await apiClient.get<{ id: number; name: string }[]>(`/groups/${groupId}/vaults`);
  return response.data.map((vault) => vault.id);
}

export async function getUserGroups(userId: number): Promise<{ groups: Group[] }> {
  const response = await apiClient.get<{ groups: Group[] }>(`/users/${userId}/groups`);
  return response.data;
}

export async function updateUserGroups(userId: number, groupIds: number[]): Promise<void> {
  await apiClient.put(`/users/${userId}/groups`, { group_ids: groupIds });
}

// ============================================================================
// Vault-Group Interfaces and Functions
// ============================================================================

export interface GroupVault {
  id: number;
  name: string;
}

export interface VaultGroupAccess {
  group_id: number;
  permission: string;
}

export async function getVaultGroups(vaultId: number): Promise<{ groups: Array<{ id: number; name: string }> }> {
  const response = await apiClient.get<{ groups: Array<{ id: number; name: string }> }>(`/vaults/${vaultId}/groups`);
  return response.data;
}

export async function updateVaultGroups(
  vaultId: number,
  groupAccess: { groupId: number; permission: string }[]
): Promise<void> {
  await apiClient.put(`/vaults/${vaultId}/groups`, { group_ids: groupAccess.map(ga => ga.groupId) });
}

// ============================================================================
// Chat Message Functions (TODO: Not yet implemented in backend)
// ============================================================================

// export interface ChatMessageUpdateRequest {
//   content: string;
// }

// TODO: editMessage endpoint not yet implemented in backend
// export async function editMessage(
//   sessionId: number,
//   messageId: number,
//   content: string
// ): Promise<ChatSessionMessage> {
//   const request: ChatMessageUpdateRequest = { content };
//   const response = await apiClient.patch<ChatSessionMessage>(
//     `/chat/sessions/${sessionId}/messages/${messageId}`,
//     request
//   );
//   return response.data;
// }

// TODO: regenerateMessage endpoint not yet implemented in backend
// export async function regenerateMessage(
//   sessionId: number,
//   messageId: number
// ): Promise<ChatSessionMessage> {
//   const response = await apiClient.post<ChatSessionMessage>(
//     `/chat/sessions/${sessionId}/messages/${messageId}/regenerate`
//   );
//   return response.data;
// }

// TODO: exportChatSession endpoint not yet implemented in backend
// export async function exportChatSession(sessionId: number): Promise<Blob> {
//   const response = await apiClient.get<Blob>(`/chat/sessions/${sessionId}/export`, {
//     responseType: "blob",
//   });
//   return response.data;
// }

export default apiClient;
