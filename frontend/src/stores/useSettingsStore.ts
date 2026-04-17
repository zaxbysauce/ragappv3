import { create } from "zustand";
import type { SettingsResponse } from "@/lib/api";

export interface SettingsFormData {
  chunk_size_chars: number;
  chunk_overlap_chars: number;
  retrieval_top_k: number;
  auto_scan_enabled: boolean;
  auto_scan_interval_minutes: number;
  max_distance_threshold: number;
  retrieval_window: number;
  vector_metric: string;
  embedding_doc_prefix: string;
  embedding_query_prefix: string;
  embedding_batch_size: number;
  // Retrieval settings
  reranking_enabled: boolean;
  reranker_url: string;
  reranker_model: string;
  initial_retrieval_top_k: number;
  reranker_top_n: number;
  hybrid_search_enabled: boolean;
  hybrid_alpha: number;
  // Model connection settings
  ollama_embedding_url: string;
  ollama_chat_url: string;
  embedding_model: string;
  chat_model: string;
}

export interface SettingsErrors {
  chunk_size_chars?: string;
  chunk_overlap_chars?: string;
  retrieval_top_k?: string;
  auto_scan_interval_minutes?: string;
  max_distance_threshold?: string;
  retrieval_window?: string;
  vector_metric?: string;
  embedding_doc_prefix?: string;
  embedding_query_prefix?: string;
  embedding_batch_size?: string;
  reranker_url?: string;
  reranker_model?: string;
  initial_retrieval_top_k?: string;
  reranker_top_n?: string;
  hybrid_alpha?: string;
  // Model connection settings
  ollama_embedding_url?: string;
  ollama_chat_url?: string;
  embedding_model?: string;
  chat_model?: string;
}

export interface SettingsState {
  // Data state
  settings: SettingsResponse | null;
  formData: SettingsFormData;
  
  // Loading state
  loading: boolean;
  saving: boolean;
  
  // Error/Status state
  error: string | null;
  errors: SettingsErrors;
  saveStatus: "idle" | "success" | "error";

  // Actions
  setSettings: (settings: SettingsResponse | null) => void;
  setFormData: (formData: SettingsFormData | ((prev: SettingsFormData) => SettingsFormData)) => void;
  updateFormField: <K extends keyof SettingsFormData>(
    field: K,
    value: SettingsFormData[K]
  ) => void;
  setLoading: (loading: boolean) => void;
  setSaving: (saving: boolean) => void;
  setError: (error: string | null) => void;
  setErrors: (errors: SettingsErrors) => void;
  setSaveStatus: (status: "idle" | "success" | "error") => void;
  
  // Initialize form from settings
  initializeForm: (settings: SettingsResponse) => void;
  
  // Validation
  validateForm: () => boolean;
  
  // Check if form has changes
  hasChanges: () => boolean;
  
  // Reset state
  resetState: () => void;
}

const defaultFormData: SettingsFormData = {
  chunk_size_chars: 2000,
  chunk_overlap_chars: 200,
  retrieval_top_k: 5,
  auto_scan_enabled: false,
  auto_scan_interval_minutes: 60,
  max_distance_threshold: 0.7,
  retrieval_window: 1,
  vector_metric: "cosine",
  embedding_doc_prefix: "Passage: ",
  embedding_query_prefix: "Query: ",
  embedding_batch_size: 32,
  reranking_enabled: false,
  reranker_url: "",
  reranker_model: "",
  initial_retrieval_top_k: 20,
  reranker_top_n: 5,
  hybrid_search_enabled: false,
  hybrid_alpha: 0.5,
  ollama_embedding_url: "",
  ollama_chat_url: "",
  embedding_model: "",
  chat_model: "",
};

export const useSettingsStore = create<SettingsState>((set, get) => ({
  // Initial state
  settings: null,
  formData: { ...defaultFormData },
  loading: true,
  saving: false,
  error: null,
  errors: {},
  saveStatus: "idle",

  // Actions
  setSettings: (settings) => {
    set({ settings });
  },

  setFormData: (formData) => {
    if (typeof formData === "function") {
      set((state) => ({ formData: formData(state.formData) }));
    } else {
      set({ formData });
    }
  },

  updateFormField: (field, value) => {
    set((state) => ({
      formData: { ...state.formData, [field]: value },
      saveStatus: "idle",
    }));
  },

  setLoading: (loading) => {
    set({ loading });
  },

  setSaving: (saving) => {
    set({ saving });
  },

  setError: (error) => {
    set({ error });
  },

  setErrors: (errors) => {
    set({ errors });
  },

  setSaveStatus: (saveStatus) => {
    set({ saveStatus });
  },

  initializeForm: (settings) => {
    set({
      formData: {
        chunk_size_chars: settings.chunk_size_chars ?? 2000,
        chunk_overlap_chars: settings.chunk_overlap_chars ?? 200,
        retrieval_top_k: settings.retrieval_top_k ?? 5,
        auto_scan_enabled: settings.auto_scan_enabled ?? false,
        auto_scan_interval_minutes: settings.auto_scan_interval_minutes ?? 60,
        max_distance_threshold: settings.max_distance_threshold ?? 0.7,
        retrieval_window: settings.retrieval_window ?? 1,
        vector_metric: settings.vector_metric ?? "cosine",
        embedding_doc_prefix: settings.embedding_doc_prefix ?? "Passage: ",
        embedding_query_prefix: settings.embedding_query_prefix ?? "Query: ",
        embedding_batch_size: settings.embedding_batch_size ?? 32,
        reranking_enabled: settings.reranking_enabled ?? false,
        reranker_url: settings.reranker_url ?? "",
        reranker_model: settings.reranker_model ?? "",
        initial_retrieval_top_k: settings.initial_retrieval_top_k ?? 20,
        reranker_top_n: settings.reranker_top_n ?? 5,
        hybrid_search_enabled: settings.hybrid_search_enabled ?? false,
        hybrid_alpha: settings.hybrid_alpha ?? 0.5,
        // Model connection settings
        ollama_embedding_url: settings.ollama_embedding_url ?? "",
        ollama_chat_url: settings.ollama_chat_url ?? "",
        embedding_model: settings.embedding_model ?? "",
        chat_model: settings.chat_model ?? "",
      },
      loading: false,
      error: null,
    });
  },

  validateForm: () => {
    const { formData } = get();
    const newErrors: SettingsErrors = {};

    // Validate positive integers
    if (formData.chunk_size_chars <= 0) {
      newErrors.chunk_size_chars = "Chunk size must be a positive integer";
    }
    if (formData.chunk_overlap_chars <= 0) {
      newErrors.chunk_overlap_chars = "Chunk overlap must be a positive integer";
    }
    if (formData.retrieval_top_k <= 0) {
      newErrors.retrieval_top_k = "Retrieval top-k must be a positive integer";
    }
    if (formData.auto_scan_interval_minutes <= 0) {
      newErrors.auto_scan_interval_minutes = "Scan interval must be a positive integer";
    }
    if (formData.embedding_batch_size < 1 || formData.embedding_batch_size > 128) {
      newErrors.embedding_batch_size = "Embedding batch size must be between 1 and 128";
    }

    // Validate overlap < size
    if (formData.chunk_overlap_chars >= formData.chunk_size_chars) {
      newErrors.chunk_overlap_chars = "Chunk overlap must be less than chunk size";
    }

    // Validate threshold is between 0 and 1
    if (formData.max_distance_threshold < 0 || formData.max_distance_threshold > 1) {
      newErrors.max_distance_threshold = "Distance threshold must be between 0 and 1";
    }

    // Validate retrieval window (0-3)
    if (formData.retrieval_window < 0 || formData.retrieval_window > 3) {
      newErrors.retrieval_window = "Retrieval window must be between 0 and 3";
    }

    // Validate vector metric
    const validMetrics = ["cosine", "euclidean", "dot_product"];
    if (!validMetrics.includes(formData.vector_metric)) {
      newErrors.vector_metric = "Vector metric must be cosine, euclidean, or dot_product";
    }

    // Validate retrieval settings
    if (formData.initial_retrieval_top_k !== undefined && (formData.initial_retrieval_top_k < 5 || formData.initial_retrieval_top_k > 100)) {
      newErrors.initial_retrieval_top_k = "Initial retrieval top-k must be between 5 and 100";
    }
    if (formData.reranker_top_n !== undefined && (formData.reranker_top_n < 1 || formData.reranker_top_n > 20)) {
      newErrors.reranker_top_n = "Reranker top-n must be between 1 and 20";
    }
    if (formData.hybrid_alpha !== undefined && (formData.hybrid_alpha < 0 || formData.hybrid_alpha > 1)) {
      newErrors.hybrid_alpha = "Hybrid alpha must be between 0 and 1";
    }

    // Validate model connection settings
    if (formData.ollama_embedding_url && !/^https?:\/\//.test(formData.ollama_embedding_url)) {
      newErrors.ollama_embedding_url = "URL must start with http:// or https://";
    }
    if (formData.ollama_chat_url && !/^https?:\/\//.test(formData.ollama_chat_url)) {
      newErrors.ollama_chat_url = "URL must start with http:// or https://";
    }

    set({ errors: newErrors });
    return Object.keys(newErrors).length === 0;
  },

  hasChanges: () => {
    const { settings, formData } = get();
    if (!settings) return false;
    return (
      formData.chunk_size_chars !== (settings.chunk_size_chars ?? 2000) ||
      formData.chunk_overlap_chars !== (settings.chunk_overlap_chars ?? 200) ||
      formData.retrieval_top_k !== (settings.retrieval_top_k ?? 5) ||
      formData.auto_scan_enabled !== (settings.auto_scan_enabled ?? false) ||
      formData.auto_scan_interval_minutes !== (settings.auto_scan_interval_minutes ?? 60) ||
      formData.max_distance_threshold !== (settings.max_distance_threshold ?? 0.7) ||
      formData.retrieval_window !== (settings.retrieval_window ?? 1) ||
      formData.vector_metric !== (settings.vector_metric ?? "cosine") ||
      formData.embedding_doc_prefix !== (settings.embedding_doc_prefix ?? "Passage: ") ||
      formData.embedding_query_prefix !== (settings.embedding_query_prefix ?? "Query: ") ||
      formData.embedding_batch_size !== (settings.embedding_batch_size ?? 32) ||
       formData.reranking_enabled !== (settings.reranking_enabled ?? false) ||
       formData.reranker_url !== (settings.reranker_url ?? "") ||
       formData.reranker_model !== (settings.reranker_model ?? "") ||
       formData.initial_retrieval_top_k !== (settings.initial_retrieval_top_k ?? 20) ||
       formData.reranker_top_n !== (settings.reranker_top_n ?? 5) ||
       formData.hybrid_search_enabled !== (settings.hybrid_search_enabled ?? false) ||
       formData.hybrid_alpha !== (settings.hybrid_alpha ?? 0.5) ||
       formData.ollama_embedding_url !== (settings.ollama_embedding_url ?? "") ||
       formData.ollama_chat_url !== (settings.ollama_chat_url ?? "") ||
       formData.embedding_model !== (settings.embedding_model ?? "") ||
       formData.chat_model !== (settings.chat_model ?? "")
    );
  },

  resetState: () => {
    set({
      settings: null,
      formData: { ...defaultFormData },
      loading: true,
      saving: false,
      error: null,
      errors: {},
      saveStatus: "idle",
    });
  },

  // Alias for resetState to match task requirements
  reset: () => {
    set({
      settings: null,
      formData: { ...defaultFormData },
      loading: true,
      saving: false,
      error: null,
      errors: {},
      saveStatus: "idle",
    });
  },
}));
