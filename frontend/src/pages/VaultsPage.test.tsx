import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

vi.mock("@/lib/api", () => ({
  listOrganizations: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/stores/useVaultStore", () => ({
  useVaultStore: vi.fn(() => ({
    vaults: [
      {
        id: 1,
        name: "Default",
        description: "",
        file_count: 0,
        memory_count: 0,
        session_count: 0,
        is_default: true,
        current_user_permission: "admin",
      },
      {
        id: 2,
        name: "Admin Vault",
        description: "",
        file_count: 0,
        memory_count: 0,
        session_count: 0,
        current_user_permission: "admin",
      },
      {
        id: 3,
        name: "Write Vault",
        description: "",
        file_count: 0,
        memory_count: 0,
        session_count: 0,
        current_user_permission: "write",
      },
    ],
    loading: false,
    fetchVaults: vi.fn(),
    addVault: vi.fn(),
    editVault: vi.fn(),
    removeVault: vi.fn(),
    activeVaultId: 2,
    setActiveVault: vi.fn(),
  })),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/components/ui/card", () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    disabled,
    title,
    onClick,
  }: {
    children: React.ReactNode;
    disabled?: boolean;
    title?: string;
    onClick?: () => void;
  }) => (
    <button disabled={disabled} title={title} onClick={onClick}>
      {children}
    </button>
  ),
}));

vi.mock("@/components/ui/input", () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));

vi.mock("@/components/ui/label", () => ({
  Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => (
    <label {...props}>{children}</label>
  ),
}));

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => <div />,
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
}));

vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}));

vi.mock("lucide-react", () => ({
  Brain: () => <span />,
  Database: () => <span />,
  FileText: () => <span />,
  Loader2: () => <span />,
  MessageSquare: () => <span />,
  Pencil: () => <span>Edit icon</span>,
  Plus: () => <span />,
  Shield: () => <span />,
  Trash2: () => <span>Delete icon</span>,
}));

import VaultsPage from "@/pages/VaultsPage";

describe("VaultsPage permission gating", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses each vault permission and default status for edit/delete controls", async () => {
    render(<VaultsPage />);

    expect(await screen.findByText("Admin Vault")).toBeInTheDocument();

    expect(screen.getByTitle("Edit vault")).not.toBeDisabled();
    expect(screen.getByTitle("Delete vault")).not.toBeDisabled();

    for (const button of screen.getAllByTitle("Default vault cannot be modified")) {
      expect(button).toBeDisabled();
    }
    for (const button of screen.getAllByTitle("Vault admin permission is required")) {
      expect(button).toBeDisabled();
    }
  });
});
