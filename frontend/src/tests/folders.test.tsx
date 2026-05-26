/**
 * Folder hierarchy tests: FolderTree sidebar (tree building, selection,
 * expand/collapse, inline create) and MoveToFolderDialog (folder picker +
 * move call).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

const moveDocumentsToFolder = vi.fn();
vi.mock("@/lib/api", () => ({
  moveDocumentsToFolder: (...args: unknown[]) => moveDocumentsToFolder(...args),
}));

import { FolderTree } from "@/components/documents/FolderTree";
import { MoveToFolderDialog } from "@/components/documents/MoveToFolderDialog";
import type { Folder } from "@/lib/api";

const folder = (id: number, name: string, parent: number | null = null): Folder => ({
  id,
  vault_id: 1,
  parent_folder_id: parent,
  name,
  description: "",
  created_at: "",
  updated_at: "",
  document_count: 0,
});

function renderTree(overrides: Partial<Parameters<typeof FolderTree>[0]> = {}) {
  const props = {
    folders: [folder(1, "Parent"), folder(2, "Child", 1), folder(3, "Sibling")],
    selectedFolderId: null,
    onSelect: vi.fn(),
    canMutate: true,
    onCreate: vi.fn().mockResolvedValue(undefined),
    onRename: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn(),
    ...overrides,
  };
  render(<FolderTree {...props} />);
  return props;
}

describe("FolderTree", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders root folders and the All documents entry", () => {
    renderTree();
    expect(screen.getByText("All documents")).toBeInTheDocument();
    expect(screen.getByText("Parent")).toBeInTheDocument();
    expect(screen.getByText("Sibling")).toBeInTheDocument();
    // Child is nested and collapsed by default.
    expect(screen.queryByText("Child")).not.toBeInTheDocument();
  });

  it("selects a folder and the All documents entry", () => {
    const { onSelect } = renderTree();
    fireEvent.click(screen.getByText("Parent"));
    expect(onSelect).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByText("All documents"));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("expands a parent to reveal its child", () => {
    renderTree();
    fireEvent.click(screen.getByRole("button", { name: "Expand folder" }));
    expect(screen.getByText("Child")).toBeInTheDocument();
  });

  it("creates a root folder via the inline input", async () => {
    const { onCreate } = renderTree();
    fireEvent.click(screen.getByRole("button", { name: "New folder" }));
    const input = screen.getByLabelText("New folder name");
    fireEvent.change(input, { target: { value: "Fresh" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("Fresh", null));
  });

  it("hides mutation controls when canMutate is false", () => {
    renderTree({ canMutate: false });
    expect(screen.queryByRole("button", { name: "New folder" })).not.toBeInTheDocument();
  });
});

describe("MoveToFolderDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  const baseProps = {
    open: true,
    onOpenChange: vi.fn(),
    vaultId: 1,
    selectedFileIds: [10, 11],
    folders: [folder(1, "Parent"), folder(2, "Child", 1)],
    onMoved: vi.fn(),
  };

  it("moves documents into the selected folder", async () => {
    moveDocumentsToFolder.mockResolvedValue({ moved: 2 });
    const onMoved = vi.fn();
    render(<MoveToFolderDialog {...baseProps} onMoved={onMoved} />);

    fireEvent.click(screen.getByRole("radio", { name: "Parent" }));
    fireEvent.click(screen.getByRole("button", { name: "Move" }));

    await waitFor(() =>
      expect(moveDocumentsToFolder).toHaveBeenCalledWith(1, [10, 11], 1)
    );
    await waitFor(() => expect(onMoved).toHaveBeenCalled());
  });

  it("moves documents to root when 'No folder' is chosen", async () => {
    moveDocumentsToFolder.mockResolvedValue({ moved: 2 });
    render(<MoveToFolderDialog {...baseProps} />);

    // Default selection is root (null); just click Move.
    fireEvent.click(screen.getByRole("button", { name: "Move" }));

    await waitFor(() =>
      expect(moveDocumentsToFolder).toHaveBeenCalledWith(1, [10, 11], null)
    );
  });
});
