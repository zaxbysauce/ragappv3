import { FileText, FileType, Sheet, File } from "lucide-react";

/**
 * Returns a colored Lucide icon component for the given filename based on extension.
 * Always use via JSX: <FileIcon filename={doc.filename} className="h-4 w-4" />
 */
export function FileIcon({ filename, className }: { filename: string | null | undefined; className?: string }) {
  const ext = (filename ?? '').split('.').pop()?.toLowerCase() ?? '';

  if (ext === 'pdf') {
    return <FileType className={className} style={{ color: '#ef4444' }} aria-hidden="true" />;
  }
  if (ext === 'docx' || ext === 'doc') {
    return <FileType className={className} style={{ color: '#3b82f6' }} aria-hidden="true" />;
  }
  if (ext === 'md' || ext === 'mdx') {
    return <FileText className={className} style={{ color: '#14b8a6' }} aria-hidden="true" />;
  }
  if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') {
    return <Sheet className={className} style={{ color: '#22c55e' }} aria-hidden="true" />;
  }
  if (ext === 'txt') {
    return <FileText className={className} style={{ color: undefined }} aria-hidden="true" />;
  }
  return <File className={className} aria-hidden="true" />;
}
