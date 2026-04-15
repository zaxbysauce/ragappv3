import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Brain, Plus, Search, Trash2, Loader2 } from "lucide-react";
import { useVaultStore } from "@/stores/useVaultStore";
import { VaultSelector } from "@/components/vault/VaultSelector";
import { useMemorySearch } from "@/hooks/useMemorySearch";
import { useMemoryCrud, getCategoryFromMetadata, getTagsFromMetadata, getSourceFromMetadata, MAX_MEMORY_CONTENT_LENGTH } from "@/hooks/useMemoryCrud";

export default function MemoryPage() {
  const { activeVaultId } = useVaultStore();

  // Hook 1: Memory search/list functionality
  const { memories, searchQuery, setSearchQuery, loading, handleSearch } = useMemorySearch(activeVaultId);

  // Hook 2: Memory CRUD operations
  const {
    isAddDialogOpen,
    setIsAddDialogOpen,
    newMemory,
    setNewMemory,
    isSubmitting,
    isDeleting,
    contentError,
    handleContentChange,
    handleAddMemory,
    handleKeyDown,
    handleDeleteMemory,
  } = useMemoryCrud(activeVaultId, handleSearch);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Memory</h1>
          <p className="text-muted-foreground mt-1">View and manage AI memory and context</p>
        </div>
        <div className="flex items-center gap-2">
          <VaultSelector />
          <Button onClick={() => setIsAddDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Add Memory
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search memories..."
            className="pl-10"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
        </div>
        <Button onClick={handleSearch} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
          Search
        </Button>
        <Badge variant="secondary">{memories?.length || 0} memories</Badge>
      </div>

      {isAddDialogOpen && (
        <Card>
          <CardHeader>
            <CardTitle>Add New Memory</CardTitle>
            <CardDescription>Create a new memory entry for the AI</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="memory-content">Content *</Label>
              <Textarea
                id="memory-content"
                placeholder="Enter memory content..."
                className={`min-h-[100px] ${contentError ? "border-destructive focus-visible:ring-destructive" : ""}`}
                value={newMemory.content}
                onChange={handleContentChange}
                onKeyDown={handleKeyDown}
              />
              {contentError && (
                <span className="text-xs text-destructive">{contentError}</span>
              )}
              <div className="flex justify-end">
                <span className={`text-xs ${newMemory.content.length > MAX_MEMORY_CONTENT_LENGTH ? "text-destructive" : "text-muted-foreground"}`}>
                  {newMemory.content.length}/{MAX_MEMORY_CONTENT_LENGTH}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="memory-category">Category</Label>
                <Input
                  id="memory-category"
                  placeholder="e.g., facts, preferences"
                  value={newMemory.category}
                  onChange={(e) => setNewMemory({ ...newMemory, category: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="memory-source">Source</Label>
                <Input
                  id="memory-source"
                  placeholder="e.g., user input, document"
                  value={newMemory.source}
                  onChange={(e) => setNewMemory({ ...newMemory, source: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="memory-tags">Tags</Label>
              <Input
                id="memory-tags"
                placeholder="Enter tags separated by commas..."
                value={newMemory.tags}
                onChange={(e) => setNewMemory({ ...newMemory, tags: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleAddMemory} disabled={isSubmitting || !newMemory.content.trim()}>
                {isSubmitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
                Add Memory
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && (!memories || memories.length === 0) ? (
        <div className="space-y-4">
          {[...Array(4)].map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-3">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-[90%]" />
                    <Skeleton className="h-4 w-[60%]" />
                    <div className="flex flex-wrap items-center gap-2 pt-2">
                      <Skeleton className="h-5 w-[70px]" />
                      <Skeleton className="h-5 w-[50px]" />
                      <Skeleton className="h-5 w-[60px]" />
                    </div>
                  </div>
                  <Skeleton className="h-8 w-8 shrink-0" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : !memories || memories.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Brain className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              {searchQuery ? "No memories match your search" : "No memories yet. Add some to get started."}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {memories?.map((memory) => (
            <Card key={memory.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <p className="text-sm whitespace-pre-wrap">{memory.content}</p>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{getCategoryFromMetadata(memory.metadata)}</Badge>
                      {getTagsFromMetadata(memory.metadata).map((tag, index) => (
                        <Badge key={index} variant="secondary" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                      {getSourceFromMetadata(memory.metadata) && (
                        <span className="text-xs text-muted-foreground">
                          Source: {getSourceFromMetadata(memory.metadata)}
                        </span>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={() => handleDeleteMemory(memory.id)}
                    disabled={isDeleting === memory.id}
                    aria-label="Delete memory"
                  >
                    {isDeleting === memory.id ? (
                      <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" aria-hidden="true" />
                    ) : (
                      <Trash2 className="w-4 h-4 text-destructive" aria-hidden="true" />
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
