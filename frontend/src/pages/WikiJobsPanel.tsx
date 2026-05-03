import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { RefreshCw, RotateCcw, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  listWikiJobs,
  retryWikiJob,
  cancelWikiJob,
  recompileVaultWiki,
  type WikiCompileJob,
} from "@/lib/api";

const STATUS_COLORS: Record<WikiCompileJob["status"], string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  completed: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  cancelled: "bg-muted text-muted-foreground line-through",
};

const TRIGGER_LABELS: Record<WikiCompileJob["trigger_type"], string> = {
  ingest: "Ingest",
  query: "Query",
  memory: "Memory",
  manual: "Manual",
  settings_reindex: "Reindex",
};

interface WikiJobsPanelProps {
  vaultId: number;
}

export function WikiJobsPanel({ vaultId }: WikiJobsPanelProps) {
  const [jobs, setJobs] = useState<WikiCompileJob[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listWikiJobs({ vault_id: vaultId, status: statusFilter || undefined });
      setJobs(res.jobs);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [vaultId, statusFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleRetry(jobId: number) {
    setActionLoading(jobId);
    try {
      await retryWikiJob(jobId, vaultId);
      toast.success("Job queued for retry");
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCancel(jobId: number) {
    setActionLoading(jobId);
    try {
      await cancelWikiJob(jobId, vaultId);
      toast.success("Job cancelled");
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Cancel failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRecompile() {
    setLoading(true);
    try {
      const res = await recompileVaultWiki(vaultId);
      toast.success(`Recompile job queued (id: ${res.job_id})`);
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Recompile failed");
    } finally {
      setLoading(false);
    }
  }

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="text-sm font-semibold shrink-0">Compile Jobs</h3>
        <div className="flex items-center gap-2">
          <select
            className="text-xs border border-input rounded px-2 py-1 bg-background"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
          </Button>
          <Button variant="outline" size="sm" onClick={handleRecompile} disabled={loading}>
            <RotateCcw className="w-3.5 h-3.5 mr-1" />
            Recompile
          </Button>
        </div>
      </div>

      {/* Job list */}
      {jobs.length === 0 && !loading && (
        <p className="text-xs text-muted-foreground text-center py-4">No jobs found.</p>
      )}

      {jobs.map((job) => (
        <Card key={job.id} className="text-sm">
          <CardContent className="py-2 px-3 flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-mono text-xs text-muted-foreground shrink-0">#{job.id}</span>
                <span className="font-medium truncate">
                  {TRIGGER_LABELS[job.trigger_type] ?? job.trigger_type}
                </span>
                {job.trigger_id && (
                  <span className="text-xs text-muted-foreground truncate">{job.trigger_id}</span>
                )}
              </div>
              <span
                className={`text-xs rounded px-1.5 py-0.5 shrink-0 font-medium ${STATUS_COLORS[job.status] ?? ""}`}
              >
                {job.status}
              </span>
            </div>

            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Created {formatDate(job.created_at)}</span>
              {job.completed_at && <span>Done {formatDate(job.completed_at)}</span>}
            </div>

            {job.error && (
              <p className="text-xs text-destructive truncate" title={job.error}>
                {job.error}
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-1.5 mt-0.5">
              {job.status === "failed" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 text-xs"
                  disabled={actionLoading === job.id}
                  onClick={() => handleRetry(job.id)}
                >
                  {actionLoading === job.id ? (
                    <Loader2 className="w-3 h-3 animate-spin mr-1" />
                  ) : (
                    <RotateCcw className="w-3 h-3 mr-1" />
                  )}
                  Retry
                </Button>
              )}
              {(job.status === "pending" || job.status === "running") && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 text-xs"
                  disabled={actionLoading === job.id}
                  onClick={() => handleCancel(job.id)}
                >
                  {actionLoading === job.id ? (
                    <Loader2 className="w-3 h-3 animate-spin mr-1" />
                  ) : (
                    <X className="w-3 h-3 mr-1" />
                  )}
                  Cancel
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
