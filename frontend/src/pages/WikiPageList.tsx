import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, Plus, Trash2, RefreshCw } from "lucide-react";
import type { WikiPage } from "@/lib/api";
import { bulkWikiPageAction } from "@/lib/api";

const PAGE_TYPES = [
  { value: "", label: "All" },
  { value: "overview", label: "Overview" },
  { value: "entity", label: "Entities" },
  { value: "system", label: "Systems" },
  { value: "procedure", label: "Procedures" },
  { value: "acronym", label: "Acronyms" },
  { value: "qa", label: "Q&A" },
  { value: "contradiction", label: "Contradictions" },
  { value: "open_question", label: "Open Questions" },
] as const;

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  verified: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  stale: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  needs_review: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  archived: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

interface WikiPageListProps {
  pages: WikiPage[];
  loading: boolean;
  onSelect: (pageId: number) => void;
  onFilter: (params: { page_type?: string; search?: string }) => void;
  onCreateClick: () => void;
  vaultId?: number | null;
}

export function WikiPageList({ pages, loading, onSelect, onFilter, onCreateClick, vaultId }: WikiPageListProps) {
  const [search, setSearch] = useState("");
  const [activeType, setActiveType] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkLoading, setBulkLoading] = useState(false);

  // Clear selection when pages change
  useEffect(() => {
    setSelectedIds([]);
  }, [pages]);

  function toggleSelect(pageId: number, e: React.MouseEvent) {
    e.stopPropagation();
    setSelectedIds((prev) =>
      prev.includes(pageId) ? prev.filter((id) => id !== pageId) : [...prev, pageId]
    );
  }

  function toggleSelectAll() {
    if (selectedIds.length === pages.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(pages.map((p) => p.id));
    }
  }

  async function handleBulkDelete() {
    if (!vaultId || selectedIds.length === 0) return;
    if (!window.confirm(`Delete ${selectedIds.length} selected page(s)?`)) return;
    setBulkLoading(true);
    try {
      await bulkWikiPageAction(vaultId, selectedIds, "delete");
      setSelectedIds([]);
      onFilter({ page_type: activeType || undefined, search: search || undefined });
    } catch {
      // error handled by api interceptor
    } finally {
      setBulkLoading(false);
    }
  }

  async function handleBulkStatusChange(status: string) {
    if (!vaultId || selectedIds.length === 0) return;
    setBulkLoading(true);
    try {
      await bulkWikiPageAction(vaultId, selectedIds, "update", { status });
      setSelectedIds([]);
      onFilter({ page_type: activeType || undefined, search: search || undefined });
    } catch {
      // error handled by api interceptor
    } finally {
      setBulkLoading(false);
    }
  }

  useEffect(() => {
    onFilter({ page_type: activeType || undefined, search: search || undefined });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeType]);

  function handleSearch() {
    onFilter({ page_type: activeType || undefined, search: search || undefined });
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Search + create */}
      <div className="flex gap-2">
        <Input
          placeholder="Search wiki..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          className="flex-1"
        />
        <Button variant="outline" size="icon" onClick={handleSearch} aria-label="Search">
          <Search className="w-4 h-4" />
        </Button>
        <Button onClick={onCreateClick} size="sm">
          <Plus className="w-4 h-4 mr-1" />
          New Page
        </Button>
      </div>

      {/* Type filter tabs */}
      <Tabs value={activeType} onValueChange={setActiveType}>
        <TabsList className="flex-wrap h-auto gap-1">
          {PAGE_TYPES.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="text-xs">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Bulk action bar */}
      {selectedIds.length > 0 && (
        <div className="flex items-center gap-2 px-2 py-2 bg-muted/50 rounded-md border border-border">
          <span className="text-xs font-medium">{selectedIds.length} selected</span>
          <Button
            variant="outline"
            size="sm"
            onClick={handleBulkDelete}
            disabled={bulkLoading}
            className="text-destructive hover:text-destructive text-xs h-7"
          >
            <Trash2 className="w-3 h-3 mr-1" />
            Delete
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleBulkStatusChange("draft")}
            disabled={bulkLoading}
            className="text-xs h-7"
          >
            <RefreshCw className="w-3 h-3 mr-1" />
            Set Draft
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleBulkStatusChange("archived")}
            disabled={bulkLoading}
            className="text-xs h-7"
          >
            Archive
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedIds([])}
            className="text-xs h-7 ml-auto"
          >
            Clear
          </Button>
        </div>
      )}

      {/* Page list */}
      <div className="flex flex-col gap-2 overflow-y-auto flex-1">
        {loading && (
          <p className="text-sm text-muted-foreground text-center py-8">Loading...</p>
        )}
        {!loading && pages.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">No pages found.</p>
        )}
        {!loading && pages.length > 0 && (
          <div className="flex items-center gap-2 px-1 mb-1">
            <input
              type="checkbox"
              checked={selectedIds.length === pages.length && pages.length > 0}
              onChange={toggleSelectAll}
              className="h-3.5 w-3.5 rounded border-border"
              aria-label="Select all pages"
            />
            <span className="text-xs text-muted-foreground">Select all</span>
          </div>
        )}
        {pages.map((page) => (
          <Card
            key={page.id}
            className={`cursor-pointer hover:bg-secondary/50 transition-colors ${selectedIds.includes(page.id) ? "ring-2 ring-primary/50" : ""}`}
            onClick={() => onSelect(page.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && onSelect(page.id)}
          >
            <CardContent className="py-3 px-4">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(page.id)}
                  onClick={(e) => toggleSelect(page.id, e)}
                  onChange={() => {}}
                  className="h-3.5 w-3.5 mt-1 rounded border-border shrink-0"
                  aria-label={`Select ${page.title}`}
                />
                <div className="flex items-start justify-between gap-2 flex-1 min-w-0">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{page.title}</p>
                    <p className="text-xs text-muted-foreground truncate">{page.slug}</p>
                    {page.summary && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{page.summary}</p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <Badge variant="outline" className="text-xs capitalize">{page.page_type}</Badge>
                    <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${STATUS_COLORS[page.status] ?? ""}`}>
                      {page.status}
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
