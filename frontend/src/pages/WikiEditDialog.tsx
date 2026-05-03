import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WikiPage } from "@/lib/api";

const PAGE_TYPES = [
  "entity", "procedure", "system", "acronym", "qa",
  "contradiction", "open_question", "overview", "manual",
] as const;

const STATUSES = ["draft", "needs_review", "verified", "stale", "archived"] as const;

interface WikiEditDialogProps {
  open: boolean;
  page?: WikiPage | null;
  vaultId: number;
  onClose: () => void;
  onSave: (data: {
    title: string;
    page_type: string;
    slug?: string;
    markdown: string;
    summary: string;
    status: string;
    confidence: number;
  }) => Promise<void>;
}

export function WikiEditDialog({ open, page, vaultId: _vaultId, onClose, onSave }: WikiEditDialogProps) {
  const [title, setTitle] = useState("");
  const [pageType, setPageType] = useState<string>("entity");
  const [slug, setSlug] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [summary, setSummary] = useState("");
  const [status, setStatus] = useState<string>("draft");
  const [confidence, setConfidence] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (page) {
      setTitle(page.title);
      setPageType(page.page_type);
      setSlug(page.slug);
      setMarkdown(page.markdown);
      setSummary(page.summary);
      setStatus(page.status);
      setConfidence(page.confidence);
    } else {
      setTitle("");
      setPageType("entity");
      setSlug("");
      setMarkdown("");
      setSummary("");
      setStatus("draft");
      setConfidence(0);
    }
    setError(null);
  }, [page, open]);

  async function handleSave() {
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({ title, page_type: pageType, slug: slug || undefined, markdown, summary, status, confidence });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{page ? "Edit Page" : "New Wiki Page"}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div>
            <Label htmlFor="wiki-title">Title</Label>
            <Input id="wiki-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Page title" />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <Label htmlFor="wiki-type">Type</Label>
              <Select value={pageType} onValueChange={setPageType}>
                <SelectTrigger id="wiki-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_TYPES.map((t) => (
                    <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <Label htmlFor="wiki-status">Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id="wiki-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => (
                    <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label htmlFor="wiki-slug">Slug (optional — auto-generated from title)</Label>
            <Input id="wiki-slug" value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="auto" />
          </div>

          <div>
            <Label htmlFor="wiki-summary">Summary</Label>
            <Input id="wiki-summary" value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One-line summary" />
          </div>

          <div>
            <Label htmlFor="wiki-markdown">Content (Markdown)</Label>
            <Textarea
              id="wiki-markdown"
              value={markdown}
              onChange={(e) => setMarkdown(e.target.value)}
              placeholder="Page content…"
              rows={6}
              className="font-mono text-sm"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
