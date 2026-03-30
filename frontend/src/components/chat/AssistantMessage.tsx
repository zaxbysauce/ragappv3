// frontend/src/components/chat/AssistantMessage.tsx
// Business logic implementation for assistant message display with citations

import { useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import { Bot, Copy, Check, RotateCcw, Bug, ChevronRight, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Message } from "@/stores/useChatStore";
import type { Source } from "@/lib/api";
import { useChatShellStore } from "@/stores/useChatShellStore";
import { getRelevanceLabel, type ScoreType } from "@/lib/relevance";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

// =============================================================================
// TYPES & INTERFACES
// =============================================================================

interface AssistantMessageProps {
  /** The message data */
  message: Message;
  /** Whether this message is currently streaming */
  isStreaming?: boolean;
  /** Callback when a source citation is clicked */
  onSourceClick?: (source: Source) => void;
  /** Callback when "View all sources" is clicked */
  onViewAllSources?: () => void;
  /** Callback when copy button is clicked */
  onCopy?: () => void;
  /** Callback when retry button is clicked */
  onRetry?: () => void;
  /** Callback when debug toggle is clicked */
  onDebugToggle?: (isActive: boolean) => void;
}

interface CitationChipProps {
  /** The source to display */
  source: Source;
  /** Index for display */
  index: number;
  /** Click handler */
  onClick: () => void;
}

interface EvidenceStripProps {
  /** List of sources to display */
  sources: Source[];
  /** Callback when a source is clicked */
  onSourceClick: (source: Source) => void;
  /** Callback when "View all" is clicked */
  onViewAll: () => void;
}

interface ParsedContent {
  /** Text segments and citation placeholders */
  segments: Array<{ type: "text"; content: string } | { type: "citation"; sourceName: string }>;
  /** Unique sources found in citations */
  citedSources: Source[];
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Parse citations from message content using regex.
 * Matches [Source: filename] tags and extracts source names.
 */
export function parseCitations(content: string, sources: Source[] | undefined): ParsedContent {
  const regex = /\[Source:\s*([^\]]+)\]/g;
  const segments: ParsedContent["segments"] = [];
  const citedSources: Source[] = [];
  const seenSourceIds = new Set<string>();

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(content)) !== null) {
    // Add text before the citation
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        content: content.slice(lastIndex, match.index),
      });
    }

    const sourceName = match[1].trim();
    segments.push({
      type: "citation",
      sourceName,
    });

    // Find the corresponding source in the sources array
    const source = sources?.find((s) => s.filename === sourceName);
    if (source && !seenSourceIds.has(source.id)) {
      citedSources.push(source);
      seenSourceIds.add(source.id);
    }

    lastIndex = regex.lastIndex;
  }

  // Add remaining text after last citation
  if (lastIndex < content.length) {
    segments.push({
      type: "text",
      content: content.slice(lastIndex),
    });
  }

  return { segments, citedSources };
}

// =============================================================================
// SUB-COMPONENTS
// =============================================================================

/**
 * CitationChip - Clickable chip showing a cited source
 */
function CitationChip({ source, index, onClick }: CitationChipProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs",
        "bg-primary/10 text-primary hover:bg-primary/20 transition-colors",
        "border border-primary/20"
      )}
      aria-label={`Source ${index + 1}: ${source.filename}`}
    >
      <FileText className="h-3 w-3" />
      <span className="truncate max-w-[120px]">{source.filename}</span>
    </button>
  );
}

/**
 * EvidenceStrip - Horizontal strip of citation chips with "View all" link
 */
function EvidenceStrip({ sources, onSourceClick, onViewAll }: EvidenceStripProps) {
  if (sources.length === 0) return null;

  const displaySources = sources.slice(0, 3);
  const remainingCount = sources.length - 3;

  return (
    <div className="flex items-center gap-2 flex-wrap mt-3">
      <span className="text-xs text-muted-foreground">Sources:</span>
      {displaySources.map((source, index) => {
        const relevance = source.score !== undefined
          ? getRelevanceLabel(source.score, source.score_type as ScoreType)
          : null;
        return (
          <div key={source.id} className="flex items-center gap-1.5">
            <CitationChip
              source={source}
              index={index}
              onClick={() => onSourceClick(source)}
            />
            {relevance && (
              <Badge variant="outline" className={cn("text-[10px]", relevance.color)}>
                {relevance.text}
              </Badge>
            )}
          </div>
        );
      })}
      {remainingCount > 0 && (
        <button
          onClick={onViewAll}
          className="text-xs text-primary hover:underline"
          aria-label={`View all ${sources.length} sources`}
        >
          +{remainingCount} more
        </button>
      )}
      {sources.length > 3 && (
        <button
          onClick={onViewAll}
          className="inline-flex items-center gap-0.5 text-xs text-primary hover:underline ml-1"
          aria-label="View all sources"
        >
          View all
          <ChevronRight className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

/**
 * ActionBar - Copy, Retry, Debug action buttons
 */
interface ActionBarProps {
  /** Whether to show the copy button */
  showCopy?: boolean;
  /** Whether to show the retry button */
  showRetry?: boolean;
  /** Whether to show the debug button */
  showDebug?: boolean;
  /** Content to copy */
  content: string;
  /** Callback when copy is clicked */
  onCopy?: () => void;
  /** Callback when retry is clicked */
  onRetry?: () => void;
  /** Callback when debug is clicked */
  onDebugToggle?: (isActive: boolean) => void;
  /** Whether debug mode is active */
  isDebugActive?: boolean;
}

function ActionBar({
  showCopy = true,
  showRetry = true,
  showDebug = true,
  content,
  onCopy,
  onRetry,
  onDebugToggle,
  isDebugActive = false,
}: ActionBarProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      onCopy?.();
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Silently fail if clipboard is not available
    }
  }, [content, onCopy]);

  return (
    <div className="flex items-center gap-1 mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
      <TooltipProvider>
        {showCopy && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={handleCopy}
                aria-label={copied ? "Copied" : "Copy message"}
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-green-500" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>{copied ? "Copied!" : "Copy"}</p>
            </TooltipContent>
          </Tooltip>
        )}

        {showRetry && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onRetry}
                aria-label="Retry"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Retry</p>
            </TooltipContent>
          </Tooltip>
        )}

        {showDebug && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className={cn("h-7 w-7", isDebugActive && "bg-accent text-accent-foreground")}
                onClick={() => onDebugToggle?.(!isDebugActive)}
                aria-label="Toggle debug info"
              >
                <Bug className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Debug</p>
            </TooltipContent>
          </Tooltip>
        )}
      </TooltipProvider>
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function AssistantMessage({
  message,
  isStreaming = false,
  onSourceClick,
  onViewAllSources,
  onCopy,
  onRetry,
  onDebugToggle,
}: AssistantMessageProps) {
  const [isDebugActive, setIsDebugActive] = useState(false);
  const { openRightPane, setSelectedEvidenceSource, setActiveRightTab } = useChatShellStore();

  // Parse citations from message content
  const { segments, citedSources } = useMemo(() => {
    return parseCitations(message.content, message.sources);
  }, [message.content, message.sources]);

  // Handle citation click - open right pane and select source
  const handleSourceClick = useCallback(
    (source: Source) => {
      // Update store state
      setSelectedEvidenceSource(source);
      setActiveRightTab("evidence");
      openRightPane();

      // Also call the external handler if provided
      onSourceClick?.(source);
    },
    [setSelectedEvidenceSource, setActiveRightTab, openRightPane, onSourceClick]
  );

  // Handle "View all sources" click
  const handleViewAllSources = useCallback(() => {
    setActiveRightTab("evidence");
    openRightPane();
    onViewAllSources?.();
  }, [setActiveRightTab, openRightPane, onViewAllSources]);

  // Handle debug toggle
  const handleDebugToggle = useCallback(() => {
    const newState = !isDebugActive;
    setIsDebugActive(newState);
    onDebugToggle?.(newState);
  }, [isDebugActive, onDebugToggle]);

  // Render content with inline citation chips
  const renderContent = () => {
    return segments.map((segment, index) => {
      if (segment.type === "citation") {
        const source = message.sources?.find((s) => s.filename === segment.sourceName);
        if (source) {
          // Find the chip index by looking up the source in citedSources to handle duplicates correctly
          const sourceIndex = citedSources.findIndex((s) => s.id === source.id);
          // Use sourceIndex + 1 for display (sourceIndex is -1 if not found)
          const displayIndex = sourceIndex >= 0 ? sourceIndex : index;
          return (
            <CitationChip
              key={index}
              source={source}
              index={displayIndex}
              onClick={() => handleSourceClick(source)}
            />
          );
        }
        // If source not found, render as plain text
        return <span key={index}>[Source: {segment.sourceName}]</span>;
      }
      // For text segments, render markdown
      return (
        <ReactMarkdown
          key={index}
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeSanitize]}
          components={{
            // Override to prevent nesting issues
            p: ({ children }) => <>{children}</>,
          }}
        >
          {segment.content}
        </ReactMarkdown>
      );
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex gap-3 p-4 bg-muted/30 group"
      role="article"
      aria-label="Assistant message"
    >
      {/* Avatar */}
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-muted"
        aria-hidden="true"
      >
        <Bot className="h-4 w-4" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span className="font-semibold text-sm">Assistant</span>
          {isStreaming && (
            <span className="text-xs text-muted-foreground animate-pulse">thinking...</span>
          )}
        </div>

        {/* Message Body */}
        <div className="prose prose-sm dark:prose-invert max-w-none">
          {renderContent()}
          {isStreaming && (
            <span className="inline-block w-2 h-4 ml-1 bg-foreground animate-pulse" />
          )}
        </div>

        {/* Evidence Strip - show cited sources */}
        {citedSources.length > 0 && (
          <EvidenceStrip
            sources={citedSources}
            onSourceClick={handleSourceClick}
            onViewAll={handleViewAllSources}
          />
        )}

        {/* Show all sources if no inline citations but sources exist */}
        {citedSources.length === 0 && message.sources && message.sources.length > 0 && (
          <EvidenceStrip
            sources={message.sources}
            onSourceClick={handleSourceClick}
            onViewAll={handleViewAllSources}
          />
        )}

        {/* Error State */}
        {message.error && (
          <div className="mt-2 text-sm text-destructive">{message.error}</div>
        )}

        {/* Stopped State */}
        {message.stopped && !message.error && (
          <div className="mt-2 text-sm text-muted-foreground italic">Generation stopped</div>
        )}

        {/* Action Bar */}
        {!isStreaming && (
          <ActionBar
            content={message.content}
            onCopy={onCopy}
            onRetry={onRetry}
            onDebugToggle={handleDebugToggle}
            isDebugActive={isDebugActive}
          />
        )}

        {/* Debug Info */}
        {isDebugActive && (
          <div className="mt-3 p-3 rounded-lg bg-muted border text-xs font-mono">
            <div className="text-muted-foreground mb-1">Debug Info:</div>
            <div>Message ID: {message.id}</div>
            <div>Sources: {message.sources?.length || 0}</div>
            <div>Cited: {citedSources.length}</div>
            <div>Content length: {message.content.length} chars</div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export default AssistantMessage;
