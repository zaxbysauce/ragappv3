/**
 * Utility functions for formatting common data types
 */

/**
 * Format a file size in bytes to a human-readable string
 * @param bytes - The file size in bytes
 * @returns A formatted string like "1.5 MB" or "0 B" if bytes is falsy
 */
export function formatFileSize(bytes?: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

/**
 * Format a date string to a localized date string
 * @param dateStr - The ISO date string to format
 * @returns A localized date string or "Unknown" if dateStr is falsy
 */
export function formatDate(dateStr?: string): string {
  if (!dateStr) return "Unknown";
  return new Date(dateStr).toLocaleDateString();
}

/**
 * Format a date string as a relative time label (e.g. "just now", "5m ago", "Yesterday")
 * @param dateString - The ISO date string to format
 * @returns A human-readable relative time string
 */
export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(dateString);
}
