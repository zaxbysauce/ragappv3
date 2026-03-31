import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { FileText, Upload, Search, Trash2, ScanLine, AlertCircle, Loader2, X, RotateCcw, Trash } from "lucide-react";
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
  const [filenameColWidth, setFilenameColWidth] = useState<number>(250);
  const dragState = useRef<{ startX: number; startWidth: number }>({ startX: 0, startWidth: 0 });

  // Cleanup on unmount: restore cursor if component is destroyed during a drag
  useEffect(() => {
    return () => {
      document.body.style.cursor = '';
    };
  }, []);

  // Global upload store
  const { uploads, addUploads, cancelUpload, removeUpload, clearCompleted, retryUpload } = useUploadStore();
  const { activeVaultId } = useVaultStore();

  const fetchDocuments = useCallback(async () => {
    try {
      const response = await listDocuments(activeVaultId ?? undefined);
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

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchDocuments(), fetchStats()]);
      setLoading(false);
    };
    loadData();
  }, [fetchDocuments, fetchStats]);

  // Status polling for documents in processing state
  useEffect(() => {
    const hasProcessingDocs = documents?.some(
      (doc) => doc.metadata?.status === "processing" || doc.metadata?.status === "pending"
    );

    if (!hasProcessingDocs) return;

    const interval = setInterval(() => {
      fetchDocuments();
      fetchStats();
    }, 5000);

    return () => clearInterval(interval);
  }, [documents, fetchDocuments, fetchStats]);

  // Refresh documents when uploads complete
  useEffect(() => {
    const completedCount = uploads.filter((u) => u.status === "completed").length;
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

  const handleBulkDelete = useCallback(async () => {
    if (selectedIds.size === 0) return;
    
    const confirmMsg = `Are you sure you want to delete ${selectedIds.size} document${selectedIds.size > 1 ? 's' : ''}?`;
    if (!window.confirm(confirmMsg)) return;

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

  const handleDeleteAllInVault = useCallback(async () => {
    if (!documents || documents.length === 0) return;
    if (!activeVaultId) {
      toast.error("No vault selected");
      return;
    }

    const confirmMsg = `Are you sure you want to delete ALL documents in this vault? This action cannot be undone.`;
    if (!window.confirm(confirmMsg)) return;

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
  }, [documents.length, activeVaultId]);

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
    accept: {
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
      'text/markdown': ['.md'],
    },
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

  const handleDeleteDocument = async (docId: string) => {
    if (!confirm("Are you sure you want to delete this document? This will also remove all associated chunks.")) return;
    try {
      await deleteDocument(docId);
      toast.success("Document deleted successfully");
      await Promise.all([fetchDocuments(), fetchStats()]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete document");
    }
  };

  const filteredDocuments = useMemo(
    () => documents?.filter((doc) =>
      doc.filename.toLowerCase().includes(debouncedSearchQuery.toLowerCase())
    ) ?? [],
    [documents, debouncedSearchQuery]
  );

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
                {uploads.filter((u) => u.status === "completed").length} completed
              </CardDescription>
            </div>
            {uploads.some((u) => u.status === "completed" || u.status === "error" || u.status === "cancelled") && (
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
                    {upload.status === "completed" && (
                      <span className="text-green-500 text-xs">Done</span>
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
                    {(upload.status === "completed" || upload.status === "cancelled" || upload.status === "error") && (
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
                  <Progress value={upload.progress} className="h-1.5" />
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {rejectedFiles.length > 0 && (
        <div className="p-4 bg-amber-500/10 text-amber-700 rounded-lg">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-5 h-5" />
            <span className="font-medium">Some files were rejected:</span>
          </div>
          <ul className="list-disc pl-5 space-y-1">
            {rejectedFiles.map((file, index) => (
              <li key={index} className="text-sm">{file}</li>
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
              <div className="overflow-x-auto">
                <table className="w-full" style={{ tableLayout: 'fixed' }}>
                  <caption className="sr-only">Documents List</caption>
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th scope="col" className="text-left p-4 font-medium">
                        <Checkbox 
                          checked={(selectedIds.size > 0 && selectedIds.size === filteredDocuments.length) ?? false}
                          onCheckedChange={handleSelectAll}
                          aria-label="Select all documents"
                        />
                      </th>
                      <th
                        scope="col"
                        className="text-left p-4 font-medium relative"
                        style={{ width: filenameColWidth }}
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
                      <th scope="col" className="text-left p-4 font-medium">Status</th>
                      <th scope="col" className="text-left p-4 font-medium">Chunks</th>
                      <th scope="col" className="text-left p-4 font-medium">Size</th>
                      <th scope="col" className="text-left p-4 font-medium">Uploaded</th>
                      <th scope="col" className="text-right p-4 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDocuments.map((doc) => {
                      const docId = String(doc.id);
                      const isSelected = Boolean(selectedIds.has(docId));
                      return (
                        <tr key={doc.id} className={`border-b hover:bg-muted/50 ${isSelected ? 'bg-muted/30' : ''}`}>
                          <td className="p-4">
                            <Checkbox 
                              checked={isSelected ?? false}
                              onCheckedChange={(checked) => handleSelectOne(String(doc.id), !!checked)}
                              aria-label={`Select ${doc.filename}`}
                            />
                          </td>
                          <td className="p-4">
                            <div className="flex items-center gap-2">
                              <FileText className="w-4 h-4 text-muted-foreground" />
                              <span className="font-medium truncate max-w-full" title={doc.filename}>{doc.filename}</span>
                            </div>
                          </td>
                          <td className="p-4"><StatusBadge status={doc.metadata?.status as string} /></td>
                          <td className="p-4">{String(doc.metadata?.chunk_count ?? 0)}</td>
                          <td className="p-4">{formatFileSize(doc.size)}</td>
                          <td className="p-4 text-muted-foreground">{formatDate(doc.created_at)}</td>
                          <td className="p-4 text-right">
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="min-w-[44px] min-h-[44px]" 
                              onClick={() => handleDeleteDocument(String(doc.id))}
                            >
                              <Trash2 className="w-4 h-4 text-destructive" />
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
           <div className="grid grid-cols-1 gap-3 sm:hidden">
             {filteredDocuments.map((doc) => (
               <DocumentCard
                 key={doc.id}
                 document={doc}
                 onDelete={(id) => handleDeleteDocument(String(id))}
                 isSelected={selectedIds.has(doc.id)}
                 onSelectionChange={handleSelectOne}
               />
             ))}
           </div>
        </>
      )}
    </div>
  );
}
