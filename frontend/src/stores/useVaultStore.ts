import { create } from "zustand";
import type { Vault } from "@/lib/api";
import { listVaults, createVault, updateVault, deleteVault } from "@/lib/api";
import type { VaultCreateRequest, VaultUpdateRequest } from "@/lib/api";

const storedVaultId = localStorage.getItem("kv_active_vault_id");
const parsed = storedVaultId ? parseInt(storedVaultId, 10) : NaN;
const initialVaultId = Number.isNaN(parsed) ? null : parsed;

export interface VaultState {
  // State
  vaults: Vault[];
  activeVaultId: number | null;
  loading: boolean;
  error: string | null;
  // Actions
  fetchVaults: () => Promise<void>;
  setActiveVault: (id: number | null) => void;
  addVault: (request: VaultCreateRequest) => Promise<Vault>;
  editVault: (id: number, request: VaultUpdateRequest) => Promise<Vault>;
  removeVault: (id: number) => Promise<void>;
  getActiveVault: () => Vault | undefined;
}

export const useVaultStore = create<VaultState>((set, get) => ({
  // Initial state
  vaults: [],
  activeVaultId: initialVaultId,
  loading: false,
  error: null,

  // Actions
  fetchVaults: async () => {
    set({ loading: true, error: null });
    try {
      const data = await listVaults();
      set({ vaults: data.vaults, loading: false, error: null });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to fetch vaults";
      set({ error: errorMessage, loading: false });
    }
  },

  setActiveVault: (id: number | null) => {
    if (id != null) {
      localStorage.setItem("kv_active_vault_id", String(id));
    } else {
      localStorage.removeItem("kv_active_vault_id");
    }
    set({ activeVaultId: id });
  },

  addVault: async (request: VaultCreateRequest) => {
    const newVault = await createVault(request);
    set((state) => ({ vaults: [...state.vaults, newVault] }));
    return newVault;
  },

  editVault: async (id: number, request: VaultUpdateRequest) => {
    const updatedVault = await updateVault(id, request);
    set((state) => ({ vaults: state.vaults.map((v) => (v.id === id ? updatedVault : v)) }));
    return updatedVault;
  },

  removeVault: async (id: number) => {
    await deleteVault(id);
    set((state) => {
      const isActiveVault = state.activeVaultId === id;
      if (isActiveVault) {
        localStorage.removeItem("kv_active_vault_id");
      }
      return {
        vaults: state.vaults.filter((v) => v.id !== id),
        ...(isActiveVault && { activeVaultId: null }),
      };
    });
  },

  getActiveVault: () => {
    const { vaults, activeVaultId } = get();
    if (!vaults || !Array.isArray(vaults)) return undefined;
    return vaults.find((v) => v.id === activeVaultId);
  },
}));
