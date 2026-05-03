import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useDropzone, type FileRejection } from "react-dropzone";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FileText, Upload, Search, Trash2, ScanLine, AlertCircle, Loader2, X, RotateCcw, Trash, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { FileIcon } from "@/lib/fileIcon";
import { listDocuments, scanDocuments, deleteDocument, deleteDocuments, deleteAllDocumentsInVault, getDocumentStats, type Document, type DocumentStatsResponse } from "@/lib/api";
import { formatFileSize, formatDate } from "@/lib/formatters";
import { useDebounce } from "@/hooks/useDebounce";
import { useVaultStore } from "@/stores/useVaultStore";
import { useUploadStore } from "@/stores/useUploadStore";
import { VaultSelector } from "@/components/vault/VaultSelector";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { DocumentCard } from "@/components/shared/DocumentCard";
import { EmptyState } from "@/components/shared/EmptyState";

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [stats, setStats] = useState<DocumentStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, isSearching] = useDebounce(searchQuery, 300);
  const [isScanning, setIsScanning] = useState(false);
  const [rejectedFiles, setRejectedFiles] = useState<string[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [isBulkDeletingAll, setIsBulkDeletingAll] = useState(false);
  // H-28 fix: Replace window.confirm with Dialog
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void;
    variant?: "destructive" | "default";
  }>({ open: false, title: "", description: "", onConfirm: () => {} });
  // Persist the resizable filename column width across reloads.
  const FILENAME_COL_WIDTH_KEY = "ragapp_doc_table_filename_col";
  const FILENAME_COL_WIDTH_DEFAULT = 250;
  const [filenameColWidth, setFilenameColWidth] = useState<number>(() => {
    if (typeof window === "undefined") return FILENAME_COL_WIDTH_DEFAULT;
    try {
      const stored = window.localStorage.getItem(FILENAME_COL_WIDTH_KEY);
      const parsed = stored ? parseInt(stored, 10) : NaN;
      if (Number.isFinite(parsed) && parsed >= 120 && parsed <= 600) return parsed;
    } catch {
      // ignore
    }
    return FILENAME_COL_WIDTH_DEFAULT;
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(FILENAME_COL_WIDTH_KEY, String(filenameColWidth));
    } catch {
      // ignore (quota / private mode)
    }
  }, [filenameColWidth]);
  const dragState = useRef<{ startX: number; startWidth: number }>({ startX: 0, startWidth: 0 });
  const pollIntervalMsRef = useRef(2_000);
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const mobileScrollRef = useRef<HTMLDivElement>(null);
  // Optimistic delete state
  const [optimisticallyDeletedIds, setOptimisticallyDeletedIds] = useState<Set<string>>(new Set());
  const pendingDeleteTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Cleanup on unmount: restore cursor if component is destroyed during a drag
  useEffect(() => {
    return () => {
      document.body.style.cursor = '';
    };
  }, []);

  // Cleanup pending delete timers on unmount
  useEffect(() => {
    return () => {
      // eslint-disable-next-line react-hooks/exhaustive-deps
      pendingDeleteTimersRef.current.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  // Global upload store
  const { uploads, addUploads, cancelUpload, removeUpload, clearCompleted, retryUpload } = useUploadStore();
  const { activeVaultId } = useVaultStore();

  const fetchDocuments = useCallback(async (search?: string) => {
    try {
      const response = await listDocuments(activeVaultId ?? undefined, search);
      setDocuments(response?.documents || []);
    } catch (err) {
      console.error("Failed to fetch documents:", err);
      toast.error(err instanceof Error ? err.message : "Failed to load documents");
      setDocuments([]);
    }
  }, [activeVaultId]);

  const fetchStats = useCallback(async () => {
    try {
      const response = await getDocumentStats(activeVaultId ?? undefined);
      setStats(response);
    } catch (err) {
      console.error("Failed to fetch stats:", err);
      toast.error(err instanceof Error ? err.message : "Failed to load document stats");
    }
  }, [activeVaultId]);

  const handleResizeMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragState.current = { startX: e.clientX, startWidth: filenameColWidth };
    const originalCursor = document.body.style.cursor;
    document.body.style.cursor = 'col-resize';

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - dragState.current.startX;
      const newWidth = Math.max(120, Math.min(600, dragState.current.startWidth + deltaX));
      setFilenameColWidth(newWidth);
    };

    const handleMouseUp = () => {
      document.body.style.cursor = originalCursor;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [filenameColWidth]);

  // isFirstSearchRender guards against the search effect double-firing with
  // loadData on mount AND on vault switch (fetchDocuments ref changes both times).
  const isFirstSearchRender = useRef(true);
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      isFirstSearchRender.current = true; // suppress search effect on vault switch
      await Promise.all([fetchDocuments(), fetchStats()]);
      setLoading(false);
    };
    loadData();
  }, [fetchDocuments, fetchStats]);

  // Server-side search: re-fetch when debounced search query changes.
  // Skipped on mount and vault switch — loadData already fetches.
  useEffect(() => {
    if (isFirstSearchRender.current) {
      isFirstSearchRender.current = false;
      return;
    }
    fetchDocuments(debouncedSearchQuery || undefined);
  }, [debouncedSearchQuery, fetchDocuments]);

  // Status polling for documents in processing state — adaptive backoff.
  // Starts fast (2 s) and backs off up to 30 s when no status change is detected,
  // resetting to fast whenever processing restarts.
  useEffect(() => {
    const hasProcessingDocs = documents?.some(
      (doc) => doc.metadata?.status === "processing" || doc.metadata?.status === "pending"
    );

    if (!hasProcessingDocs) {
      pollIntervalMsRef.current = 2_000;
      return;
    }

    const delay = pollIntervalMsRef.current;
    const timer = setTimeout(() => {
      pollIntervalMsRef.current = Math.min(pollIntervalMsRef.current * 1.5, 30_000);
      fetchDocuments();
      fetchStats();
    }, delay);

    return () => clearTimeout(timer);
  }, [documents, fetchDocuments, fetchStats]);

  // Refresh documents when uploads complete
  useEffect(() => {
    const completedCount = uploads.filter((u) => u.status === "indexed").length;
    if (completedCount > 0) {
      // Refresh after a short delay to allow backend processing
      const timeout = setTimeout(() => {
        fetchDocuments();
        fetchStats();
      }, 1000);
      return () => clearTimeout(timeout);
    }
  }, [uploads, fetchDocuments, fetchStats]);

  // Bulk selection handlers
  const handleSelectAll = useCallback((checked: boolean | 'indeterminate') => {
    if (checked) {
      const allIds = new Set(documents?.map((doc) => String(doc.id)) ?? []);
      setSelectedIds(allIds);
    } else {
      setSelectedIds(new Set());
    }
  }, [documents]);

  const handleSelectOne = useCallback((docId: string, checked: boolean) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (checked) {
        newSet.add(docId);
      } else {
        newSet.delete(docId);
      }
      return newSet;
    });
  }, []);

  const executeBulkDelete = useCallback(async () => {
    setIsBulkDeleting(true);
    try {
      const result = await deleteDocuments(Array.from(selectedIds));
      if (result.deleted_count > 0) {
        toast.success(`Deleted ${result.deleted_count} document${result.deleted_count > 1 ? 's' : ''}`);
        setDocuments(prev => prev.filter(doc => !selectedIds.has(doc.id)));
        setStats(prev => prev ? { ...prev, total_documents: Math.max(0, (prev.total_documents ?? 0) - result.deleted_count) } : prev);
      }
      if (result.failed_ids.length > 0) {
        toast.error(`Failed to delete ${result.failed_ids.length} document${result.failed_ids.length > 1 ? 's' : ''}`);
      }
      setSelectedIds(new Set());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete documents");
    } finally {
      setIsBulkDeleting(false);
    }
  }, [selectedIds]);

  const handleBulkDelete = useCallback(() => {
    if (selectedIds.size === 0) return;
    setConfirmDialog({
      open: true,
      title: "Delete Selected Documents",
      description: `Are you sure you want to delete ${selectedIds.size} document${selectedIds.size > 1 ? 's' : ''}? This action cannot be undone.`,
      onConfirm: executeBulkDelete,
      variant: "destructive",
    });
  }, [selectedIds, executeBulkDelete]);

  const executeDeleteAllInVault = useCallback(async () => {
    if (!activeVaultId) return;
    setIsBulkDeletingAll(true);
    try {
      const result = await deleteAllDocumentsInVault(activeVaultId);
      if (result.deleted_count > 0) {
        toast.success(`Deleted ${result.deleted_count} document${result.deleted_count > 1 ? 's' : ''}`);
        setDocuments([]);
        setStats(prev => prev ? { ...prev, total_documents: 0 } : prev);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete documents");
    } finally {
      setIsBulkDeletingAll(false);
    }
  }, [activeVaultId]);

  const handleDeleteAllInVault = useCallback(() => {
    if (!documents || documents.length === 0) return;
    if (!activeVaultId) {
      toast.error("No vault selected");
      return;
    }
    setConfirmDialog({
      open: true,
      title: "Delete All Documents in Vault",
      description: "Are you sure you want to delete ALL documents in this vault? This action cannot be undone.",
      onConfirm: executeDeleteAllInVault,
      variant: "destructive",
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documents.length, activeVaultId, executeDeleteAllInVault]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    
    addUploads(acceptedFiles, activeVaultId ?? undefined);
    setRejectedFiles([]);
    toast.success(`Added ${acceptedFiles.length} file(s) to upload queue`);
  }, [addUploads, activeVaultId]);

  const onDropRejected = useCallback((rejected: FileRejection[]) => {
    const rejectedNames = rejected.map((r) => `${r.file.name} (${r.errors.map((e) => e.message).join(', ')})`);
    setRejectedFiles(rejectedNames);
    rejectedNames.forEach((name) => {
      toast.error(`File rejected: ${name}`);
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    maxSize: MAX_FILE_SIZE,
  });

  const handleScan = async () => {
    setIsScanning(true);
    try {
      const result = await scanDocuments(activeVaultId ?? undefined);
      toast.success(`Scan complete: ${result.added} new document(s) added, ${result.scanned} scanned`);
      await Promise.all([fetchDocuments(), fetchStats()]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setIsScanning(false);
    }
  };

  const handleDeleteDocument = (docId: string) => {
    setConfirmDialog({
      open: true,
      title: "Delete Document",
      description: "Are you sure you want to delete this document? This will also remove all associated chunks.",
      onConfirm: () => {
        // Guard: prevent duplicate delete for same document
        if (pendingDeleteTimersRef.current.has(docId)) return;

        // 1. Optimistically remove from local list
        setOptimisticallyDeletedIds((prev) => new Set(prev).add(docId));

        // 2. Show undo toast
        const toastId = toast("Document deleted", {
          description: "You can undo this action",
          duration: 3000,
          action: {
            label: "Undo",
            onClick: () => {
              // Cancel the pending delete timer
              const timer = pendingDeleteTimersRef.current.get(docId);
              if (timer) {
                clearTimeout(timer);
                pendingDeleteTimersRef.current.delete(docId);
              }
              // Restore document to list
              setOptimisticallyDeletedIds((prev) => {
                const next = new Set(prev);
                next.delete(docId);
                return next;
              });
              toast.dismiss(toastId);
            },
          },
        });

        // 3. Start 3-second timer before actual API call
        const timer = setTimeout(async () => {
          pendingDeleteTimersRef.current.delete(docId);
          toast.dismiss(toastId); // Dismiss undo toast before showing success/error
          try {
            await deleteDocument(docId);
            toast.success("Document deleted successfully");
            await Promise.all([fetchDocuments(), fetchStats()]);
            // Clean up optimistic state after successful server-side delete
            setOptimisticallyDeletedIds((prev) => {
              const next = new Set(prev);
              next.delete(docId);
              return next;
            });
          } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to delete document");
            // Restore on failure
            setOptimisticallyDeletedIds((prev) => {
              const next = new Set(prev);
              next.delete(docId);
              return next;
            });
            await fetchDocuments();
          }
        }, 3000);

        pendingDeleteTimersRef.current.set(docId, timer);
      },
      variant: "destructive",
    });
  };

  // Server already filters by search query — only apply the local optimistic-delete mask.
  const filteredDocuments = useMemo(
    () => documents?.filter((doc) => !optimisticallyDeletedIds.has(doc.id)) ?? [],
    [documents, optimisticallyDeletedIds]
  );

  const tableVirtualizer = useVirtualizer({
    count: filteredDocuments.length,
    getScrollElement: () => tableScrollRef.current,
    estimateSize: () => 56,
    overscan: 5,
  });

  const mobileVirtualizer = useVirtualizer({
    count: filteredDocuments.length,
    getScrollElement: () => mobileScrollRef.current,
    estimateSize: () => 200,
    overscan: 3,
    measureElement: (el) => el?.getBoundingClientRect().height ?? 0,
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Documents</h1>
          <p className="text-muted-foreground mt-1">Manage your knowledge base documents</p>
        </div>
        <div className="flex items-center gap-2">
          <VaultSelector />
          <Button onClick={handleScan} disabled={isScanning}>
            {isScanning ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <ScanLine className="w-4 h-4 mr-2" />
            )}
            Scan Directory
          </Button>
          {filteredDocuments.length > 0 && (
            <Button 
              variant="destructive" 
              onClick={handleDeleteAllInVault} 
              disabled={isBulkDeletingAll}
            >
              {isBulkDeletingAll ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Trash className="w-4 h-4 mr-2" />
              )}
              Delete All in Vault
            </Button>
          )}
        </div>
      </div>

      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Documents</CardDescription>
              <CardTitle className="text-3xl">{stats.total_documents}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Chunks</CardDescription>
              <CardTitle className="text-3xl">{stats.total_chunks}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Size</CardDescription>
              <CardTitle className="text-3xl">{formatFileSize(stats.total_size_bytes)}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Indexed</CardDescription>
              <CardTitle className="text-3xl">{stats.documents_by_status?.indexed || 0}</CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      <Card
        {...getRootProps()}
        className={`border-2 border-dashed cursor-pointer transition-colors ${
          isDragActive ? "border-primary bg-primary/5" : "border-border"
        }`}
      >
        <input {...getInputProps()} />
        <CardContent className="py-8">
          <div className="flex flex-col items-center justify-center text-center">
            <Badge variant="secondary" className="mb-3 gap-1.5 text-xs font-medium">
              <Info className="h-3 w-3" aria-hidden="true" />
              Max 50 MB
            </Badge>
            <Upload className="w-12 h-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">
              {isDragActive ? "Drop files here..." : "Drag & drop files here, or click to select"}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Supports PDF, DOCX, TXT, MD files (max 50MB each). Uploads continue in background.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Upload Queue */}
      {uploads.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-sm">Upload Queue</CardTitle>
              <CardDescription>
                {uploads.filter((u) => u.status === "pending").length} pending,{" "}
                {uploads.filter((u) => u.status === "uploading").length} uploading,{" "}
                {uploads.filter((u) => u.status === "indexing").length} indexing,{" "}
                {uploads.filter((u) => u.status === "indexed").length} done
              </CardDescription>
            </div>
            {uploads.some((u) => u.status === "indexed" || u.status === "error" || u.status === "cancelled") && (
              <Button variant="ghost" size="sm" onClick={clearCompleted}>
                Clear Completed
              </Button>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {uploads.map((upload) => (
              <div key={upload.id} className="space-y-2">
                <div className="flex justify-between items-center text-sm">
                  <span className="truncate max-w-[250px]" title={upload.file.name}>
                    {upload.file.name}
                  </span>
                  <div className="flex items-center gap-2">
                    {upload.status === "indexed" && (
                      <span className="text-success text-xs">Done</span>
                    )}
                    {upload.status === "indexing" && (
                      <span className="text-blue-600 text-xs">Indexing…</span>
                    )}
                    {upload.status === "error" && (
                      <span className="text-destructive text-xs" title={upload.error}>
                        Error
                      </span>
                    )}
                    {upload.status === "cancelled" && (
                      <span className="text-muted-foreground text-xs">Cancelled</span>
                    )}
                    {upload.status === "pending" && (
                      <span className="text-muted-foreground text-xs">Pending</span>
                    )}
                    {upload.status === "uploading" && (
                      <span className="text-muted-foreground text-xs">
                        {upload.progress > 0 ? `${upload.progress}%` : "Uploading..."}
                      </span>
                    )}
                    
                    {upload.status === "pending" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => cancelUpload(upload.id)}
                        aria-label={`Cancel upload for ${upload.file.name}`}
                      >
                        <X className="w-3 h-3" />
                      </Button>
                    )}
                    {upload.status === "error" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => retryUpload(upload.id)}
                        aria-label={`Retry upload for ${upload.file.name}`}
                      >
                        <RotateCcw className="w-3 h-3" />
                      </Button>
                    )}
                    {(upload.status === "indexed" || upload.status === "cancelled" || upload.status === "error") && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => removeUpload(upload.id)}
                        aria-label={`Remove ${upload.file.name} from queue`}
                      >
                        <X className="w-3 h-3" />
                      </Button>
                    )}
                  </div>
                </div>
                {upload.status === "uploading" && (
                  <Progress value={upload.progress} className="h-1.5" aria-label="Processing progress" />
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {rejectedFiles.length > 0 && (
        <div
          className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-warning-foreground"
          role="status"
          aria-live="polite"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-warning" aria-hidden="true" />
              <span className="font-medium text-foreground">
                {rejectedFiles.length === 1
                  ? "1 file was rejected"
                  : `${rejectedFiles.length} files were rejected`}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setRejectedFiles([])}
              aria-label="Dismiss rejected files list"
              className="h-7 text-xs"
            >
              Dismiss
            </Button>
          </div>
          <ul className="list-disc space-y-1 pl-5 text-sm text-foreground/80">
            {rejectedFiles.map((file, index) => (
              <li key={index}>{file}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            className="pl-10"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {isSearching && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground animate-spin" />
          )}
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.size > 0 && (
            <>
              <Badge variant="outline">{selectedIds.size} selected</Badge>
              <Button 
                variant="destructive" 
                size="sm"
                onClick={handleBulkDelete}
                disabled={isBulkDeleting}
              >
                {isBulkDeleting ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4 mr-2" />
                )}
                Delete Selected
              </Button>
            </>
          )}
          <Badge variant="secondary">{filteredDocuments.length} documents</Badge>
        </div>
      </div>

      {loading ? (
        <>
          {/* Desktop Table Skeleton (hidden on mobile) */}
          <Card className="hidden sm:block">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
              <table className="w-full">
                <caption className="sr-only">Documents List</caption>
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th scope="col" className="text-left p-4 font-medium">
                      <Checkbox disabled aria-label="Select all documents" />
                    </th>
                    <th scope="col" className="text-left p-4 font-medium">Filename</th>
                    <th scope="col" className="text-left p-4 font-medium">Status</th>
                    <th scope="col" className="text-left p-4 font-medium">Chunks</th>
                    <th scope="col" className="text-left p-4 font-medium">Size</th>
                    <th scope="col" className="text-left p-4 font-medium">Uploaded</th>
                    <th scope="col" className="text-right p-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {[...Array(5)].map((_, i) => (
                    <tr key={i} className="border-b">
                      <td className="p-4">
                        <Checkbox disabled />
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <Skeleton className="h-4 w-4" />
                          <Skeleton className="h-4 w-[180px]" />
                        </div>
                      </td>
                      <td className="p-4"><Skeleton className="h-5 w-[80px]" /></td>
                      <td className="p-4"><Skeleton className="h-4 w-[40px]" /></td>
                      <td className="p-4"><Skeleton className="h-4 w-[60px]" /></td>
                      <td className="p-4"><Skeleton className="h-4 w-[80px]" /></td>
                      <td className="p-4 text-right"><Skeleton className="h-11 w-11 ml-auto" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </CardContent>
          </Card>

          {/* Mobile Cards Skeleton (hidden on desktop) */}
          <div className="grid grid-cols-1 gap-3 sm:hidden">
            {[...Array(3)].map((_, i) => (
              <Card key={i} className="w-full">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <Skeleton className="h-11 w-11 rounded-md" />
                      <div className="min-w-0">
                        <Skeleton className="h-5 w-32 mb-1" />
                        <Skeleton className="h-4 w-24" />
                      </div>
                    </div>
                    <Skeleton className="h-11 w-11 rounded-full" />
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="space-y-1">
                      <Skeleton className="h-4 w-16" />
                      <Skeleton className="h-6 w-20" />
                    </div>
                    <div className="space-y-1">
                      <Skeleton className="h-4 w-16" />
                      <Skeleton className="h-4 w-16" />
                    </div>
                    <div className="space-y-1">
                      <Skeleton className="h-4 w-16" />
                      <Skeleton className="h-4 w-20" />
                    </div>
                    <div className="space-y-1">
                      <Skeleton className="h-4 w-16" />
                      <Skeleton className="h-4 w-12" />
                    </div>
                  </div>
                  <div className="mt-4 flex sm:hidden">
                    <Skeleton className="h-11 w-full rounded-md" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      ) : filteredDocuments.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={searchQuery ? "No documents match your search" : "No documents yet"}
          description={searchQuery ? undefined : "Upload some files to get started."}
        />
      ) : (
        <>
          {/* Desktop Table View (hidden on mobile) */}
          <Card className="hidden sm:block">
            <CardContent className="p-0">
              <div ref={tableScrollRef} className="overflow-auto" style={{ maxHeight: '70vh' }}>
                <table className="w-full" style={{ tableLayout: 'fixed' }}>
                  <caption className="sr-only">Documents List</caption>
                  <thead style={{ position: 'sticky', top: 0, zIndex: 10 }}>
                    <tr role="row" className="border-b bg-muted" style={{ display: 'flex' }}>
                      <th scope="col" className="text-left p-4 font-medium flex-none w-12">
                        <Checkbox
                          checked={selectedIds.size > 0 && selectedIds.size === filteredDocuments.length}
                          onCheckedChange={handleSelectAll}
                          aria-label="Select all documents"
                        />
                      </th>
                      <th
                        scope="col"
                        className="text-left p-4 font-medium relative flex-none"
                        style={{ width: filenameColWidth, flexShrink: 0 }}
                      >
                        Filename
                        <div
                          className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-border transition-colors"
                          onMouseDown={handleResizeMouseDown}
                          role="separator"
                          aria-orientation="vertical"
                          aria-label="Resize filename column"
                        />
                      </th>
                      <th scope="col" className="text-left p-4 font-medium flex-none w-[120px]">Status</th>
                      <th scope="col" className="text-left p-4 font-medium flex-none w-20">Chunks</th>
                      <th scope="col" className="text-left p-4 font-medium flex-none w-[100px]">Size</th>
                      <th scope="col" className="text-left p-4 font-medium flex-none w-[140px]">Uploaded</th>
                      <th scope="col" className="text-right p-4 font-medium flex-none w-[60px]">Actions</th>
                    </tr>
                  </thead>
                  <tbody role="rowgroup" style={{ height: `${tableVirtualizer.getTotalSize()}px`, position: 'relative' }}>
                    {tableVirtualizer.getVirtualItems().map((virtualItem) => {
                      const doc = filteredDocuments[virtualItem.index];
                      const docId = String(doc.id);
                      const isSelected = Boolean(selectedIds.has(docId));
                      return (
                        <tr
                          key={docId}
                          role="row"
                          data-index={virtualItem.index}
                          ref={tableVirtualizer.measureElement}
                          style={{
                            position: 'absolute',
                            top: virtualItem.start,
                            left: 0,
                            width: '100%',
                            display: 'flex',
                          }}
                          className={`border-b hover:bg-muted/50 ${isSelected ? 'bg-muted/30' : ''}`}
                        >
                          <td className="p-4 flex-none w-12">
                            <Checkbox
                              checked={isSelected}
                              onCheckedChange={(checked) => handleSelectOne(String(doc.id), !!checked)}
                              aria-label={`Select ${doc.filename}`}
                            />
                          </td>
                          <td className="p-4 flex-none" style={{ width: filenameColWidth, flexShrink: 0 }}>
                            <div className="flex items-center gap-2">
                              <FileIcon filename={doc.filename} className="w-4 h-4 flex-shrink-0" />
                              <span className="font-medium truncate max-w-full" title={doc.filename}>{doc.filename}</span>
                            </div>
                          </td>
                          <td className="p-4 flex-none w-[120px]"><StatusBadge status={doc.metadata?.status as string} /></td>
                          <td className="p-4 flex-none w-20">
                            {(() => {
                              const count = Number(doc.metadata?.chunk_count ?? 0);
                              const status = doc.metadata?.status;
                              const isIndexed = status === "indexed";
                              const isFailed = status === "error" || status === "failed";
                              return (
                                <span
                                  title={
                                    isFailed
                                      ? `${count} chunks · indexing failed`
                                      : isIndexed
                                        ? `${count} chunks indexed`
                                        : count > 0
                                          ? `${count} chunks · indexing in progress`
                                          : "Awaiting chunking"
                                  }
                                  className={cn(
                                    isFailed && "text-destructive",
                                    !isIndexed && !isFailed && count > 0 && "text-muted-foreground italic"
                                  )}
                                >
                                  {count}
                                </span>
                              );
                            })()}
                          </td>
                          <td className="p-4 flex-none w-[100px]">{formatFileSize(doc.size)}</td>
                          <td className="p-4 flex-none w-[140px] text-muted-foreground">{formatDate(doc.created_at)}</td>
                          <td className="p-4 flex-none w-[60px] text-right">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="min-w-[44px] min-h-[44px]"
                              onClick={() => handleDeleteDocument(String(doc.id))}
                              aria-label="Delete document"
                            >
                              <Trash2 className="w-4 h-4 text-destructive" aria-hidden="true" />
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

           {/* Mobile Cards View (hidden on desktop) */}
           <div ref={mobileScrollRef} className="sm:hidden" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              <div style={{ height: mobileVirtualizer.getTotalSize(), position: 'relative' }}>
                {mobileVirtualizer.getVirtualItems().map((virtualItem) => {
                  const doc = filteredDocuments[virtualItem.index];
                  const docId = String(doc.id);
                  return (
                    <div
                      key={docId}
                     data-index={virtualItem.index}
                     ref={mobileVirtualizer.measureElement}
                     style={{
                       position: 'absolute',
                       top: virtualItem.start,
                       left: 0,
                       width: '100%',
                       paddingTop: '0.75rem',
                     }}
                   >
                     <DocumentCard
                       document={doc}
                       onDelete={(id) => handleDeleteDocument(String(id))}
                       isSelected={selectedIds.has(doc.id)}
                       onSelectionChange={handleSelectOne}
                     />
                   </div>
                 );
               })}
             </div>
           </div>
        </>
      )}

      {/* Confirmation Dialog (H-28) */}
      <Dialog open={confirmDialog.open} onOpenChange={(open) => setConfirmDialog(prev => ({ ...prev, open }))}>
        <DialogContent aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-desc">
          <DialogHeader>
            <DialogTitle id="confirm-dialog-title">{confirmDialog.title}</DialogTitle>
            <DialogDescription id="confirm-dialog-desc">{confirmDialog.description}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDialog(prev => ({ ...prev, open: false }))}>
              Cancel
            </Button>
            <Button
              variant={confirmDialog.variant === "destructive" ? "destructive" : "default"}
              onClick={() => {
                setConfirmDialog(prev => ({ ...prev, open: false }));
                confirmDialog.onConfirm();
              }}
            >
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
