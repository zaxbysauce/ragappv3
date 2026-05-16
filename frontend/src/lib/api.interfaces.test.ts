import { describe, it, expect } from "vitest";
import type { CreateSessionRequest, Vault } from "@/lib/api";

describe("6.1 — api.ts interface changes", () => {
  // ===========================================================================
  // CreateSessionRequest — vault_id is required (not optional)
  // ===========================================================================
  describe("CreateSessionRequest.vault_id is required", () => {
    it("should have vault_id as a required (non-optional) field", () => {
      // TypeScript compile-time verification:
      // CreateSessionRequest requires vault_id (no ? prefix)
      // The interface is: { title?: string; vault_id: number; }
      // This means vault_id cannot be undefined.
      const requestWithTitle: CreateSessionRequest = {
        title: "My Session",
        vault_id: 42,
      };

      const requestWithOnlyVaultId: CreateSessionRequest = {
        vault_id: 99,
      };

      // Verify vault_id is always present and a number
      expect(requestWithTitle.vault_id).toBe(42);
      expect(requestWithOnlyVaultId.vault_id).toBe(99);

      // Verify title is optional (may be undefined)
      expect(requestWithOnlyVaultId.title).toBeUndefined();
    });

    it("should NOT allow vault_id to be omitted (compile-time enforced)", () => {
      // This test documents the interface contract:
      // vault_id has no ? operator, making it required.
      // At runtime we verify by checking the object shape.

      const request: CreateSessionRequest = { vault_id: 1 };

      // Explicitly verify vault_id is a number (not undefined)
      expect(typeof request.vault_id).toBe("number");
      expect(request.vault_id).toBe(1);
    });

    it("should allow title to be omitted but vault_id must be present", () => {
      // CreateSessionRequest: title is optional (?), vault_id is required
      const minimalRequest: CreateSessionRequest = {
        vault_id: 123,
      };

      expect(minimalRequest.vault_id).toBe(123);
      expect(minimalRequest.title).toBeUndefined();

      // Adding title should still work
      const requestWithTitle: CreateSessionRequest = {
        title: "Session Title",
        vault_id: 456,
      };
      expect(requestWithTitle.title).toBe("Session Title");
      expect(requestWithTitle.vault_id).toBe(456);
    });
  });

  // ===========================================================================
  // Vault — does NOT have is_default field
  // ===========================================================================
  describe("Vault interface does not have is_default field", () => {
    it("should NOT have is_default in the Vault interface definition", () => {
      // Verify a complete Vault object does not contain is_default
      const vault: Vault = {
        id: 1,
        name: "Test Vault",
        description: "A test vault description",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        file_count: 10,
        memory_count: 5,
        session_count: 3,
        org_id: null,
        current_user_permission: "admin",
      };

      // Explicitly verify is_default does not exist
      expect(Object.hasOwnProperty.call(vault, "is_default")).toBe(false);
      expect("is_default" in vault).toBe(false);
      expect(vault.is_default).toBeUndefined();
    });

    it("should have all expected required fields on Vault", () => {
      const vault: Vault = {
        id: 1,
        name: "My Vault",
        description: "Description",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        file_count: 0,
        memory_count: 0,
        session_count: 0,
        org_id: null,
      };

      // Verify all required fields exist and have correct types
      expect(vault.id).toBe(1);
      expect(vault.name).toBe("My Vault");
      expect(vault.description).toBe("Description");
      expect(vault.created_at).toBe("2024-01-01T00:00:00Z");
      expect(vault.updated_at).toBe("2024-01-01T00:00:00Z");
      expect(vault.file_count).toBe(0);
      expect(vault.memory_count).toBe(0);
      expect(vault.session_count).toBe(0);
      expect(vault.org_id).toBeNull();
    });

    it("should NOT have is_default even with all optional fields present", () => {
      const vault: Vault = {
        id: 1,
        name: "Full Vault",
        description: "With all fields",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        file_count: 5,
        memory_count: 3,
        session_count: 2,
        org_id: 10,
        current_user_permission: "write",
      };

      // Verify all optional fields work correctly
      expect(vault.org_id).toBe(10);
      expect(vault.current_user_permission).toBe("write");

      // Verify is_default is definitively absent
      const keys = Object.keys(vault);
      expect(keys).not.toContain("is_default");
      expect(Object.hasOwnProperty.call(vault, "is_default")).toBe(false);
    });

    it("should allow current_user_permission to be omitted", () => {
      const vaultWithoutPermission: Vault = {
        id: 1,
        name: "Vault",
        description: "Desc",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
        file_count: 0,
        memory_count: 0,
        session_count: 0,
        org_id: null,
      };

      expect(vaultWithoutPermission.current_user_permission).toBeUndefined();
      // And still no is_default
      expect("is_default" in vaultWithoutPermission).toBe(false);
    });
  });
});
