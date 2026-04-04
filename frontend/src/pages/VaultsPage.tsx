import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Database, Plus, Pencil, Trash2, FileText, Brain, MessageSquare, Loader2, Shield } from "lucide-react";
import { useVaultStore } from "@/stores/useVaultStore";
import type { Vault } from "@/lib/api";

export default function VaultsPage() {
  const { vaults, loading, fetchVaults, addVault, editVault, removeVault, activeVaultId, setActiveVault } = useVaultStore();
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedVault, setSelectedVault] = useState<Vault | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchVaults();
  }, [fetchVaults]);

  function openCreateDialog() {
    setName("");
    setDescription("");
    setCreateDialogOpen(true);
  }

  function openEditDialog(vault: Vault) {
    setSelectedVault(vault);
    setName(vault.name);
    setDescription(vault.description);
    setEditDialogOpen(true);
  }

  function openDeleteDialog(vault: Vault) {
    setSelectedVault(vault);
    setDeleteDialogOpen(true);
  }

  async function handleCreate() {
    if (!name.trim()) {
      toast.error("Vault name is required");
      return;
    }
    setSaving(true);
    try {
      await addVault({ name: name.trim(), description: description.trim() });
      toast.success("Vault created successfully");
      setCreateDialogOpen(false);
      setName("");
      setDescription("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create vault");
    } finally {
      setSaving(false);
    }
  }

  async function handleEdit() {
    if (!name.trim()) {
      toast.error("Vault name is required");
      return;
    }
    if (!selectedVault) return;
    setSaving(true);
    try {
      await editVault(selectedVault.id, { name: name.trim(), description: description.trim() });
      toast.success("Vault updated successfully");
      setEditDialogOpen(false);
      setSelectedVault(null);
      setName("");
      setDescription("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update vault");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!selectedVault) return;
    setDeleting(true);
    try {
      await removeVault(selectedVault.id);
      toast.success("Vault deleted successfully");
      setDeleteDialogOpen(false);
      setSelectedVault(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete vault");
    } finally {
      setDeleting(false);
    }
  }

  function handleSetActive(vaultId: number) {
    setActiveVault(vaultId);
    toast.success("Active vault changed");
  }

  if (loading && vaults.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isDefaultVault = (vault: Vault) => vault.id === 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Vaults</h1>
          <p className="text-muted-foreground">Manage your knowledge vaults</p>
        </div>
        <Button onClick={openCreateDialog}>
          <Plus className="mr-2 h-4 w-4" /> New Vault
        </Button>
      </div>

      {/* Vault Cards Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {vaults.map(vault => (
          <Card key={vault.id}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Database className="h-5 w-5 text-muted-foreground" />
                  <CardTitle className="text-lg">{vault.name}</CardTitle>
                </div>
                {vault.id === activeVaultId && (
                  <Badge variant="secondary" className="text-xs">Active</Badge>
                )}
              </div>
              <CardDescription className="mt-2">
                {vault.description || <span className="text-muted-foreground italic">No description</span>}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {/* Stat Badges */}
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    <span>{vault.file_count} files</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Brain className="h-3 w-3" />
                    <span>{vault.memory_count} memories</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" />
                    <span>{vault.session_count} sessions</span>
                  </div>
                </div>

                {/* Default Vault Badge */}
                {isDefaultVault(vault) && (
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Shield className="h-3 w-3" />
                    <Badge variant="outline" className="text-xs">Default</Badge>
                    <span className="text-xs ml-1">Cannot be modified</span>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex items-center gap-2 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleSetActive(vault.id)}
                    disabled={vault.id === activeVaultId}
                    className="flex-1"
                  >
                    Set Active
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openEditDialog(vault)}
                    disabled={isDefaultVault(vault)}
                    title={isDefaultVault(vault) ? "Default vault cannot be modified" : "Edit vault"}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openDeleteDialog(vault)}
                    disabled={isDefaultVault(vault)}
                    title={isDefaultVault(vault) ? "Default vault cannot be deleted" : "Delete vault"}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
<DialogContent aria-labelledby="create-vault-title" aria-describedby="create-vault-desc">
        <DialogHeader>
          <DialogTitle id="create-vault-title">Create New Vault</DialogTitle>
          <DialogDescription id="create-vault-desc">
            Add a new knowledge vault to organize your documents and memories.
          </DialogDescription>
        </DialogHeader>
          <div className="space-y-4">
            <div>
              <Input
                placeholder="Vault name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <Input
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                "Create"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
<DialogContent aria-labelledby="edit-vault-title" aria-describedby="edit-vault-desc">
        <DialogHeader>
          <DialogTitle id="edit-vault-title">Edit Vault</DialogTitle>
          <DialogDescription id="edit-vault-desc">
            Update vault name or description.
          </DialogDescription>
        </DialogHeader>
          <div className="space-y-4">
            <div>
              <Input
                placeholder="Vault name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <Input
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleEdit} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                "Save"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
<DialogContent aria-labelledby="delete-vault-title" aria-describedby="delete-vault-desc">
        <DialogHeader>
          <DialogTitle id="delete-vault-title">Delete Vault</DialogTitle>
          <DialogDescription id="delete-vault-desc">
            Are you sure you want to delete "{selectedVault?.name}"? This will permanently delete all documents, memories, and chat sessions in this vault. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                "Delete"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
