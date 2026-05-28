import { useEffect, useRef, useState } from "react";
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
import { AlertCircle, Layers, Activity } from "lucide-react";
import { API_BASE_URL, getWikiActivityFeed } from "@/lib/api";

export function wikiEventsUrl(vaultId: number | string): string {
  return `${API_BASE_URL}/wiki/events?vault_id=${encodeURIComponent(String(vaultId))}`;
}

export default function WikiPage() {
  const { activeVaultId } = useVaultStore();
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingPage, setEditingPage] = useState<import("@/lib/api").WikiPage | null>(null);
  const [lintPanelOpen, setLintPanelOpen] = useState(false);
  const [jobsPanelOpen, setJobsPanelOpen] = useState(false);
  const [activityPanelOpen, setActivityPanelOpen] = useState(false);
  const [activityEntries, setActivityEntries] = useState<Array<{ id: number; action: string; page_title?: string; user?: string; created_at: string }>>([]);
  const [activityLoading, setActivityLoading] = useState(false);
  const [jobsRefreshSignal, setJobsRefreshSignal] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

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

  // Subscribe to wiki compile job completion events for the active vault.
  // On any terminal job event, refetch pages, lint findings, and bump the
  // refresh signal so an open WikiJobsPanel reloads too. The auth cookie is
  // carried over withCredentials; EventSource cannot set Authorization headers.
  useEffect(() => {
    if (!activeVaultId) return;
    // jsdom (vitest) does not provide EventSource. Skip cleanly so unit tests
    // that don't exercise the live stream still mount the page.
    if (typeof EventSource === "undefined") return;
    const url = wikiEventsUrl(activeVaultId);
    const es = new EventSource(url, { withCredentials: true });
    eventSourceRef.current = es;

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as { type?: string };
        if (data.type === "job_completed" || data.type === "job_failed") {
          fetchPages();
          fetchLintFindings();
          setJobsRefreshSignal((n) => n + 1);
        }
      } catch {
        // Ignore malformed events; SSE keepalives are comment lines and never
        // reach onmessage.
      }
    };

    es.onerror = () => {
      // Browser auto-reconnects with exponential backoff for SSE. No-op here.
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeVaultId]);

  // Fetch activity feed when panel opens
  useEffect(() => {
    if (!activityPanelOpen || !activeVaultId) return;
    setActivityLoading(true);
    getWikiActivityFeed(activeVaultId, 50)
      .then((data) => setActivityEntries(Array.isArray(data) ? data : data.entries ?? []))
      .catch(() => setActivityEntries([]))
      .finally(() => setActivityLoading(false));
  }, [activityPanelOpen, activeVaultId]);

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
            onClick={() => { setActivityPanelOpen((v) => !v); setJobsPanelOpen(false); setLintPanelOpen(false); }}
          >
            <Activity className="w-4 h-4 mr-1" />
            Activity
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setJobsPanelOpen((v) => !v); setLintPanelOpen(false); setActivityPanelOpen(false); }}
          >
            <Layers className="w-4 h-4 mr-1" />
            Jobs
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setLintPanelOpen((v) => !v); setJobsPanelOpen(false); setActivityPanelOpen(false); }}
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
              vaultId={activeVaultId}
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
              vaultId={activeVaultId}
            />
          </div>
        )}

        {/* Jobs panel: right side overlay */}
        {jobsPanelOpen && activeVaultId && (
          <div className="w-80 border-l border-border p-4 overflow-y-auto shrink-0">
            <WikiJobsPanel vaultId={activeVaultId} refreshSignal={jobsRefreshSignal} />
          </div>
        )}

        {/* Activity panel: right side overlay */}
        {activityPanelOpen && activeVaultId && (
          <div className="w-80 border-l border-border p-4 overflow-y-auto shrink-0">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">Activity Feed</h3>
            </div>
            {activityLoading && <p className="text-xs text-muted-foreground">Loading...</p>}
            {!activityLoading && activityEntries.length === 0 && (
              <p className="text-xs text-muted-foreground">No recent activity.</p>
            )}
            {!activityLoading && activityEntries.length > 0 && (
              <div className="flex flex-col gap-2">
                {activityEntries.map((entry) => (
                  <div key={entry.id} className="rounded-md border border-border px-3 py-2 text-xs">
                    <div className="font-medium capitalize">{entry.action.replace(/_/g, " ")}</div>
                    {entry.page_title && (
                      <div className="text-muted-foreground truncate">{entry.page_title}</div>
                    )}
                    <div className="flex items-center gap-2 mt-1 text-muted-foreground">
                      {entry.user && <span>{entry.user}</span>}
                      <span>{new Date(entry.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
