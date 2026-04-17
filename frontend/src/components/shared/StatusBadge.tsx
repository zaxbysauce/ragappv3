import { Badge } from "@/components/ui/badge";
import { CheckCircle, Loader2, Clock, AlertCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export const FILE_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  indexed: "Indexed",
  error: "Error",
};

export const FILE_STATUS_COLORS: Record<string, { variant: "default" | "secondary" | "outline" | "destructive"; className: string; icon: LucideIcon }> = {
  pending: { variant: "outline", className: "", icon: Clock },
  processing: { variant: "secondary", className: "", icon: Loader2 },
  indexed: { variant: "default", className: "bg-success", icon: CheckCircle },
  error: { variant: "destructive", className: "", icon: AlertCircle },
};

interface StatusBadgeProps {
  status?: string;
}

/** Renders a color-coded badge for document processing status. */
export function StatusBadge({ status }: StatusBadgeProps) {
  if (!status) {
    return <Badge variant="outline">Unknown</Badge>;
  }
  const config = FILE_STATUS_COLORS[status];
  if (!config) {
    return <Badge variant="outline">Unknown</Badge>;
  }
  const Icon = config.icon;
  const label = FILE_STATUS_LABELS[status] ?? status;
  return (
    <Badge variant={config.variant} className={config.className}>
      <Icon className={`w-3 h-3 mr-1 ${status === "processing" ? "animate-spin" : ""}`} />
      {label}
    </Badge>
  );
}
