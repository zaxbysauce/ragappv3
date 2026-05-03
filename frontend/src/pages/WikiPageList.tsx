import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, Plus } from "lucide-react";
import type { WikiPage } from "@/lib/api";

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
}

export function WikiPageList({ pages, loading, onSelect, onFilter, onCreateClick }: WikiPageListProps) {
  const [search, setSearch] = useState("");
  const [activeType, setActiveType] = useState("");

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

      {/* Page list */}
      <div className="flex flex-col gap-2 overflow-y-auto flex-1">
        {loading && (
          <p className="text-sm text-muted-foreground text-center py-8">Loading…</p>
        )}
        {!loading && pages.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">No pages found.</p>
        )}
        {pages.map((page) => (
          <Card
            key={page.id}
            className="cursor-pointer hover:bg-secondary/50 transition-colors"
            onClick={() => onSelect(page.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && onSelect(page.id)}
          >
            <CardContent className="py-3 px-4">
              <div className="flex items-start justify-between gap-2">
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
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
