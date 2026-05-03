import { useEffect, useState } from "react";
import { useVaultStore } from "@/stores/useVaultStore";
import { VaultSelector } from "@/components/vault/VaultSelector";
import { WikiPageList } from "./WikiPageList";
import { WikiPageDetail } from "./WikiPageDetail";
import { WikiEditDialog } from "./WikiEditDialog";
import { WikiLintPanel } from "./WikiLintPanel";
import { WikiJobsPanel } from "./WikiJobsPanel";
import { useWikiData } from "@/hooks/useWikiData";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { AlertCircle, Layers } from "lucide-react";

export default function WikiPage() {
  const { activeVaultId } = useVaultStore();
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingPage, setEditingPage] = useState<import("@/lib/api").WikiPage | null>(null);
  const [lintPanelOpen, setLintPanelOpen] = useState(false);
  const [jobsPanelOpen, setJobsPanelOpen] = useState(false);

  const {
    pages,
    selectedPage,
    lintFindings,
    loading,
    error,
    fetchPages,
    openPage,
    closePage,
    createPage,
    editPage,
    removePage,
    fetchLintFindings,
    runLint,
  } = useWikiData(activeVaultId);

  useEffect(() => {
    if (activeVaultId) {
      fetchPages();
      fetchLintFindings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeVaultId]);

  function handleCreateClick() {
    setEditingPage(null);
    setEditDialogOpen(true);
  }

  function handleEditClick() {
    if (selectedPage) {
      setEditingPage(selectedPage);
      setEditDialogOpen(true);
    }
  }

  async function handleSave(data: Parameters<typeof createPage>[0] | Parameters<typeof editPage>[1]) {
    if (!activeVaultId) return;
    if (editingPage) {
      await editPage(editingPage.id, data as Parameters<typeof editPage>[1]);
      toast.success("Page updated");
    } else {
      const createData = data as Parameters<typeof createPage>[0];
      await createPage({ ...createData, vault_id: activeVaultId });
      toast.success("Page created");
    }
    await fetchPages();
  }

  async function handleDelete() {
    if (!selectedPage) return;
    if (!window.confirm(`Delete "${selectedPage.title}"?`)) return;
    await removePage(selectedPage.id);
    toast.success("Page deleted");
  }

  async function handleRunLint() {
    if (!activeVaultId) return;
    const findings = await runLint();
    setLintPanelOpen(true);
    toast.info(`Lint complete: ${findings.length} finding(s)`);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">Wiki</h1>
          <VaultSelector />
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setJobsPanelOpen((v) => !v); setLintPanelOpen(false); }}
          >
            <Layers className="w-4 h-4 mr-1" />
            Jobs
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setLintPanelOpen((v) => !v); setJobsPanelOpen(false); }}
          >
            <AlertCircle className="w-4 h-4 mr-1" />
            Lint {lintFindings.length > 0 && `(${lintFindings.length})`}
          </Button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel: list */}
        <div
          className={`border-r border-border p-4 flex flex-col overflow-hidden ${
            selectedPage ? "hidden md:flex md:w-80 lg:w-96 shrink-0" : "flex-1"
          }`}
        >
          {!activeVaultId ? (
            <p className="text-sm text-muted-foreground text-center py-8">Select a vault to view its wiki.</p>
          ) : (
            <WikiPageList
              pages={pages}
              loading={loading}
              onSelect={openPage}
              onFilter={(params) => fetchPages(params)}
              onCreateClick={handleCreateClick}
            />
          )}
          {error && (
            <p className="text-sm text-destructive mt-2">{error}</p>
          )}
        </div>

        {/* Right panel: detail */}
        {selectedPage && (
          <div className="flex-1 p-4 overflow-hidden">
            <WikiPageDetail
              page={selectedPage}
              onBack={closePage}
              onEdit={handleEditClick}
              onDelete={handleDelete}
            />
          </div>
        )}

        {/* Lint panel: right side overlay */}
        {lintPanelOpen && (
          <div className="w-80 border-l border-border p-4 overflow-y-auto shrink-0">
            <WikiLintPanel
              findings={lintFindings}
              loading={loading}
              onRunLint={handleRunLint}
            />
          </div>
        )}

        {/* Jobs panel: right side overlay */}
        {jobsPanelOpen && activeVaultId && (
          <div className="w-80 border-l border-border p-4 overflow-y-auto shrink-0">
            <WikiJobsPanel vaultId={activeVaultId} />
          </div>
        )}
      </div>

      {/* Edit / Create dialog */}
      {activeVaultId && (
        <WikiEditDialog
          open={editDialogOpen}
          page={editingPage}
          vaultId={activeVaultId}
          onClose={() => setEditDialogOpen(false)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
