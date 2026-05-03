import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Play } from "lucide-react";
import type { WikiLintFinding } from "@/lib/api";

const SEVERITY_COLORS: Record<string, string> = {
  low: "border-l-muted bg-muted/20",
  medium: "border-l-yellow-400 bg-yellow-50 dark:bg-yellow-950",
  high: "border-l-orange-400 bg-orange-50 dark:bg-orange-950",
  critical: "border-l-red-500 bg-red-50 dark:bg-red-950",
};

const SEVERITY_TEXT: Record<string, string> = {
  low: "text-muted-foreground",
  medium: "text-yellow-700 dark:text-yellow-300",
  high: "text-orange-700 dark:text-orange-300",
  critical: "text-red-700 dark:text-red-300",
};

interface WikiLintPanelProps {
  findings: WikiLintFinding[];
  loading: boolean;
  onRunLint: () => void;
}

export function WikiLintPanel({ findings, loading, onRunLint }: WikiLintPanelProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Lint Findings ({findings.length})</h3>
        <Button variant="outline" size="sm" onClick={onRunLint} disabled={loading}>
          <Play className="w-3.5 h-3.5 mr-1" />
          {loading ? "Running…" : "Run Lint"}
        </Button>
      </div>

      {findings.length === 0 && !loading && (
        <p className="text-xs text-muted-foreground text-center py-4">No findings. Run lint to check.</p>
      )}

      {findings.map((finding) => (
        <Card
          key={finding.id}
          className={`border-l-4 ${SEVERITY_COLORS[finding.severity] ?? ""}`}
        >
          <CardContent className="py-2 px-3">
            <div className={`text-sm font-medium ${SEVERITY_TEXT[finding.severity] ?? ""}`}>
              {finding.title}
            </div>
            {finding.details && (
              <div className="text-xs text-muted-foreground mt-0.5">{finding.details}</div>
            )}
            <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wide">
              {finding.severity} · {finding.finding_type.replace(/_/g, " ")}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
