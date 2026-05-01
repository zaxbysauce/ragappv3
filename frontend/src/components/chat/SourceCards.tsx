import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getRelevanceLabel, type ScoreType } from "@/lib/relevance";
import type { Source } from "@/lib/api";

interface SourceCardProps {
  source: Source;
  index: number;
  onClick: () => void;
}

function SourceCard({ source, index, onClick }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false);

  const relevance = source.score !== undefined
    ? getRelevanceLabel(source.score, source.score_type as ScoreType)
    : null;

  const snippet = source.snippet ?? "";
  const isLong = snippet.length > 120;
  const displaySnippet = expanded || !isLong ? snippet : snippet.slice(0, 120) + "…";

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-3 text-sm cursor-pointer",
        "hover:border-primary/30 hover:bg-accent/5 transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      aria-label={`Source ${index + 1}: ${source.filename}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary text-[10px] font-bold">
            {index + 1}
          </span>
          <span className="font-medium text-foreground truncate" title={source.filename}>
            {source.filename}
          </span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {relevance && (
            <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0", relevance.color)}>
              {relevance.text}
            </Badge>
          )}
        </div>
      </div>

      {snippet && (
        <div className="mt-2">
          <p className="text-xs text-muted-foreground leading-relaxed">{displaySnippet}</p>
          {isLong && (
            <button
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
              className="mt-1 text-[10px] text-primary hover:underline flex items-center gap-0.5"
              aria-expanded={expanded}
            >
              {expanded ? (
                <><ChevronUp className="h-3 w-3" /> Less</>
              ) : (
                <><ChevronDown className="h-3 w-3" /> More</>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

interface SourceCardsProps {
  sources: Source[];
  onSourceClick: (source: Source) => void;
  onViewAll: () => void;
  /** Don't show anything if there are no sources */
  hideIfEmpty?: boolean;
}

export function SourceCards({ sources, onSourceClick, onViewAll, hideIfEmpty = true }: SourceCardsProps) {
  const [showAll, setShowAll] = useState(false);
  const prefersReducedMotion = useReducedMotion();

  if (hideIfEmpty && sources.length === 0) return null;

  if (sources.length === 0) {
    return (
      <p className="mt-3 text-xs text-muted-foreground/60 italic">No sources found.</p>
    );
  }

  const TOP_N = 3;
  const displaySources = showAll ? sources : sources.slice(0, TOP_N);
  const remaining = sources.length - TOP_N;

  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          Sources:
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs text-primary gap-1"
          onClick={onViewAll}
          aria-label={`View all ${sources.length} sources`}
        >
          <ExternalLink className="h-3 w-3" />
          View all
        </Button>
      </div>

      <div className="space-y-1.5">
        <AnimatePresence initial={false}>
          {displaySources.map((source, i) => (
            <motion.div
              key={source.id}
              initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
              animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, height: "auto" }}
              exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
              transition={{ duration: 0.15, delay: i * 0.04 }}
              style={{ overflow: "hidden" }}
            >
              <SourceCard
                source={source}
                index={i}
                onClick={() => onSourceClick(source)}
              />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {remaining > 0 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="text-xs text-primary hover:underline"
          aria-label={`Show ${remaining} more sources`}
        >
          +{remaining} more
        </button>
      )}
    </div>
  );
}
