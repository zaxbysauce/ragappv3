import { Download, ExternalLink, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

interface PdfPreviewProps {
  blobUrl: string;
  filename: string;
  isPdf: boolean;
  pageNumber?: number | null;
}

export default function PdfPreview({
  blobUrl,
  filename,
  isPdf,
  pageNumber,
}: PdfPreviewProps) {
  const pageTarget =
    isPdf && pageNumber && pageNumber > 0 ? `${blobUrl}#page=${pageNumber}` : blobUrl;

  if (!isPdf) {
    return (
      <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-3 rounded-md border bg-muted/20 p-6 text-center">
        <FileText className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium">{filename}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Preview is available for PDF files.
          </p>
        </div>
        <Button size="sm" variant="outline" asChild>
          <a href={blobUrl} download={filename}>
            <Download className="mr-2 h-4 w-4" aria-hidden="true" />
            Download original
          </a>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-[320px] flex-col gap-2">
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="truncate">
          {pageNumber && pageNumber > 0 ? `Page ${pageNumber}` : "PDF preview"}
        </span>
        <Button size="sm" variant="ghost" asChild>
          <a href={pageTarget} target="_blank" rel="noreferrer">
            <ExternalLink className="mr-2 h-4 w-4" aria-hidden="true" />
            Open
          </a>
        </Button>
      </div>
      <iframe
        title={`Preview of ${filename}`}
        src={pageTarget}
        className="h-full min-h-[300px] w-full rounded-md border bg-background"
      />
    </div>
  );
}
