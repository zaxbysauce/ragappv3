import { create } from "zustand";
import { uploadDocument } from "@/lib/api";
import { toast } from "sonner";

export interface UploadFile {
  id: string;
  file: File;
  progress: number;
  status: "pending" | "uploading" | "completed" | "error" | "cancelled";
  error?: string;
}

interface UploadState {
  uploads: UploadFile[];
  isProcessing: boolean;
  activeVaultId: number | null;
  
  // Actions
  addUploads: (files: File[], vaultId?: number) => void;
  cancelUpload: (id: string) => void;
  removeUpload: (id: string) => void;
  updateProgress: (id: string, progress: number) => void;
  setStatus: (id: string, status: UploadFile["status"], error?: string) => void;
  setProcessing: (processing: boolean) => void;
  clearCompleted: () => void;
  retryUpload: (id: string) => void;
  processQueue: () => Promise<void>;
}

export const useUploadStore = create<UploadState>((set, get) => ({
  uploads: [],
  isProcessing: false,
  activeVaultId: null,

  addUploads: (files, vaultId) => {
    if (!vaultId) {
      toast.error("No vault selected. Please select a vault before uploading.");
      return;
    }
    const generateId = (f: File) => {
      if (typeof crypto !== "undefined" && crypto.randomUUID) {
        return crypto.randomUUID();
      }
      return `${f.name}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    };

    const newUploads: UploadFile[] = files.map((file) => ({
      id: generateId(file),
      file,
      progress: 0,
      status: "pending",
    }));

    set((state) => ({
      uploads: [...state.uploads, ...newUploads],
      activeVaultId: vaultId || state.activeVaultId,
    }));

    // Start processing if not already running
    const { isProcessing } = get();
    if (!isProcessing) {
      get().processQueue();
    }
  },

  cancelUpload: (id) => {
    set((state) => ({
      uploads: state.uploads.map((u) =>
        u.id === id && u.status === "pending" ? { ...u, status: "cancelled" } : u
      ),
    }));
    toast.info("Upload cancelled");
  },

  removeUpload: (id) => {
    set((state) => ({
      uploads: state.uploads.filter((u) => u.id !== id),
    }));
  },

  updateProgress: (id, progress) => {
    set((state) => ({
      uploads: state.uploads.map((u) =>
        u.id === id ? { ...u, progress } : u
      ),
    }));
  },

  setStatus: (id, status, error) => {
    set((state) => ({
      uploads: state.uploads.map((u) =>
        u.id === id ? { ...u, status, error } : u
      ),
    }));
  },

  setProcessing: (processing) => {
    set({ isProcessing: processing });
  },

  clearCompleted: () => {
    set((state) => ({
      uploads: state.uploads.filter(
        (u) => u.status === "pending" || u.status === "uploading"
      ),
    }));
  },

  retryUpload: (id) => {
    set((state) => ({
      uploads: state.uploads.map((u) =>
        u.id === id ? { ...u, status: "pending", progress: 0, error: undefined } : u
      ),
    }));
    
    // Start processing if not already running
    const { isProcessing } = get();
    if (!isProcessing) {
      get().processQueue();
    }
  },

  processQueue: async () => {
    let acquired = false;
    
    // Atomic check-and-set: only acquire if not already processing
    set((state) => {
      if (state.isProcessing) {
        return state;
      }
      acquired = true;
      return { ...state, isProcessing: true };
    });

    if (!acquired) {
      // Lock not acquired, another processQueue is running
      return;
    }

    try {
      while (true) {
        // Read fresh state each iteration
        const { uploads, activeVaultId } = get();
        const pendingUpload = uploads.find((u) => u.status === "pending");

        if (!pendingUpload) {
          // No more pending uploads, exit loop
          break;
        }

        // Guard against stale item: check if still pending before processing
        const currentUpload = uploads.find((u) => u.id === pendingUpload.id);
        if (!currentUpload || currentUpload.status !== "pending") {
          // Item no longer pending, continue to next iteration
          continue;
        }

        try {
          get().setStatus(pendingUpload.id, "uploading");

          await uploadDocument(
            pendingUpload.file,
            (progress) => {
              get().updateProgress(pendingUpload.id, progress);
            },
            activeVaultId || undefined
          );

          get().setStatus(pendingUpload.id, "completed");
          toast.success(`${pendingUpload.file.name} uploaded successfully`);
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : "Upload failed";
          get().setStatus(pendingUpload.id, "error", errorMsg);
          toast.error(`Failed to upload ${pendingUpload.file.name}: ${errorMsg}`);
          // Continue with next pending file on error
        }
      }
    } finally {
      set({ isProcessing: false });
      
      // If any pending uploads remain, trigger processQueue once
      const { uploads } = get();
      if (uploads.some((u) => u.status === "pending")) {
        get().processQueue();
      }
    }
  },
}));
