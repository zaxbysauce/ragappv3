// src/components/shared/DocumentCard.tsx

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { FileText, Trash2, MoreVertical } from "lucide-react";
import { StatusBadge } from "./StatusBadge";
import { formatFileSize, formatDate } from "@/lib/formatters";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface DocumentCardProps {
  /** Document data */
  document: {
    id: string;
    filename: string;
    size?: number;
    created_at?: string;
    metadata?: Record<string, unknown>;
  };
  /** Callback when delete action is triggered */
  onDelete: (id: string) => void;
  /** Loading state for delete action */
  isDeleting?: boolean;
  /** Selection state for bulk operations */
  isSelected?: boolean;
  /** Callback when selection changes */
  onSelectionChange?: (id: string, selected: boolean) => void;
}

/**
 * Mobile‑friendly card layout for document items.
 * Implements WCAG 2.1 AA requirements:
 * - Touch targets ≥44×44px
 * - Semantic HTML structure
 * - Keyboard‑accessible interactive elements
 * - Sufficient color contrast (via shadcn/ui theme)
 * - Screen‑reader labels for icons
 */
export function DocumentCard({
  document,
  onDelete,
  isDeleting = false,
  isSelected = false,
  onSelectionChange,
}: DocumentCardProps) {
  const status = document.metadata?.status as string | undefined;
  const chunkCount = document.metadata?.chunk_count as number | undefined;

  return (
    <Card
      className={`w-full overflow-hidden border-border hover:border-primary/30 transition-colors ${
        isSelected ? "ring-2 ring-primary ring-offset-2" : ""
      }`}
      role="article"
      aria-label={`Document: ${document.filename}`}
    >
      <CardContent className="p-4">
        {/* Header row: checkbox, icon, filename, actions dropdown */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            {/* Checkbox for bulk selection */}
            {onSelectionChange && (
              <Checkbox
                checked={!!isSelected}
                onCheckedChange={(checked) =>
                  onSelectionChange(document.id, !!checked)
                }
                aria-label={`Select ${document.filename}`}
                className="flex-shrink-0"
              />
            )}
            <div
              className="flex-shrink-0 p-2 bg-muted rounded-md"
              aria-hidden="true"
            >
              <FileText className="w-5 h-5 text-muted-foreground" />
            </div>
            <div className="min-w-0">
              <h3
                className="font-medium text-foreground truncate"
                title={document.filename}
              >
                {document.filename}
              </h3>
  
            </div>
          </div>

          {/* Actions dropdown (≥44×44px touch target) */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-11 w-11 flex-shrink-0"
                aria-label={`Actions for ${document.filename}`}
                aria-haspopup="menu"
              >
                <MoreVertical className="w-5 h-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem
                onClick={() => onDelete(document.id)}
                disabled={isDeleting}
                className="text-destructive focus:text-destructive"
                aria-label={`Delete ${document.filename}`}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </DropdownMenuItem>

            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Metadata row: status, size, date, chunks */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="space-y-1">
            <div className="text-muted-foreground">Status</div>
            <div>
              <StatusBadge status={status} />
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-muted-foreground">Size</div>
            <div className="text-foreground">
              {document.size ? formatFileSize(document.size) : "—"}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-muted-foreground">Uploaded</div>
            <div className="text-foreground">
              {document.created_at ? formatDate(document.created_at) : "—"}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-muted-foreground">Chunks</div>
            <div className="text-foreground">
              {chunkCount !== undefined ? String(chunkCount) : "—"}
            </div>
          </div>
        </div>

        {/* Standalone delete button (visible on larger mobile screens) */}
        <div className="mt-4 flex sm:hidden">
          <Button
            variant="destructive"
            size="sm"
            className="h-11 w-full"
            onClick={() => onDelete(document.id)}
            disabled={isDeleting}
            aria-label={`Delete ${document.filename}`}
            aria-busy={isDeleting}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            {isDeleting ? "Deleting…" : "Delete Document"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}