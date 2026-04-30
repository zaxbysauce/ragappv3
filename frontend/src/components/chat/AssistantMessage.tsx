// frontend/src/components/chat/AssistantMessage.tsx
// Business logic implementation for assistant message display with citations

import { useState, useMemo, useCallback, useEffect } from "react";
import { motion } from "framer-motion";
import { Bot, Copy, Check, RotateCcw, Bug, FileText, ThumbsUp, ThumbsDown, AlertCircle, GitBranch } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Message } from "@/stores/useChatStore";
import type { Source } from "@/lib/api";
import { updateMessageFeedback } from "@/lib/api";
import { useChatShellStore } from "@/stores/useChatShellStore";
import { getRelevanceLabel, type ScoreType } from "@/lib/relevance";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { CopyButton } from "@/components/shared/CopyButton";

// =============================================================================
// TYPES & INTERFACES
// =============================================================================

interface AssistantMessageProps {
  /** The message data */
  message: Message;
  /** Whether this message is currently streaming */
  isStreaming?: boolean;
  /** Whether to show the debug button in the action bar */
  showDebug?: boolean;
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
  /** Current feedback state for this message */
  feedback?: "up" | "down" | null;
  /** Callback when feedback is changed */
  onFeedback?: (feedback: "up" | "down" | null) => void;
  /** Callback to fork the conversation from this message */
  onFork?: () => void;
  /** Session ID for feedback API calls */
  sessionId?: string;
  /** Feedback value from server (takes priority over localStorage) */
  messageFeedback?: "up" | "down" | null;
}

interface CitationChipProps {
  /** The source to display */
  source: Source;
  /** Index for display */
  index: number;
  /** Click handler */
  onClick: () => void;
  /**
   * Visual variant:
   * - "strip" (default): full chip with FileText icon and truncated filename.
   *   Used in the EvidenceStrip below the message.
   * - "inline": compact number-only pill that fits inline in prose without
   *   breaking reading flow. The aria-label still exposes the full filename
   *   to assistive tech.
   */
  variant?: "strip" | "inline";
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
 * Supports both new stable labels [S1], [S2] and legacy [Source: filename] format.
 */
export function parseCitations(content: string, sources: Source[] | undefined): ParsedContent {
  // Match both [S1] style and legacy [Source: filename] style
  const regex = /\[S(\d+)\]|\[Source:\s*([^\]]+)\]/g;
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

    let source: Source | undefined;
    let sourceName: string;

    if (match[1]) {
      // New format: [S1], [S2], etc.
      const label = `S${match[1]}`;
      sourceName = label;
      source = sources?.find((s) => s.source_label === label);
      // Fallback: resolve by index (S1 = index 0, S2 = index 1, etc.)
      if (!source) {
        const idx = parseInt(match[1], 10) - 1;
        if (sources && idx >= 0 && idx < sources.length) {
          source = sources[idx];
        }
      }
    } else {
      // Legacy format: [Source: filename]
      sourceName = match[2].trim();
      source = sources?.find((s) => s.filename === sourceName);
    }

    segments.push({
      type: "citation",
      sourceName,
    });

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
 * CitationChip - Clickable chip showing a cited source.
 *
 * The "inline" variant renders a compact number-only pill sized to flow
 * naturally in prose. The "strip" variant (default) renders the full
 * FileText-icon + filename chip used in the EvidenceStrip below the message.
 * Using a variant lets us surface per-sentence attribution inline without
 * duplicating the heavy filename chip in both positions.
 */
function CitationChip({ source, index, onClick, variant = "strip" }: CitationChipProps) {
  const label = `Source ${index + 1}: ${source.filename}`;

  if (variant === "inline") {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center justify-center align-middle mx-0.5",
          // Baseline compact look for sighted users...
          "min-w-[22px] h-[22px] px-1.5 rounded",
          "text-[11px] font-medium leading-none",
          "bg-primary/10 text-primary hover:bg-primary/20 active:scale-95",
          "border border-primary/15 hover:border-primary/30 transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
          // ...with a 24x24 touch target on coarse pointers (mobile/tablet)
          // to clear WCAG-AA's minimum target size without enlarging the
          // visible pill in prose.
          "[@media(pointer:coarse)]:min-w-[28px] [@media(pointer:coarse)]:h-[28px]"
        )}
        aria-label={label}
        title={source.filename}
      >
        {index + 1}
      </button>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onClick}
            className={cn(
              "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs",
              "bg-primary/10 text-primary hover:bg-primary/25 active:scale-95 transition-all duration-150",
              "border border-primary/20 hover:border-primary/40 hover:shadow-sm"
            )}
            aria-label={label}
          >
            <FileText className="h-3 w-3" />
            <span className="truncate max-w-[120px]">{source.filename}</span>
          </button>
        </TooltipTrigger>
        {source.snippet && (
          <TooltipContent className="max-w-[250px] text-xs">
            <p>{source.snippet.slice(0, 100)}{source.snippet.length > 100 ? '…' : ''}</p>
          </TooltipContent>
        )}
      </Tooltip>
    </TooltipProvider>
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
    </div>
  );
}

/**
 * ActionBar - Copy, Retry, Debug, Feedback action buttons
 */
interface ActionBarProps {
  /** Whether to show the copy button */
  showCopy?: boolean;
  /** Whether to show the retry button */
  showRetry?: boolean;
  /** Whether to show the debug button */
  showDebug?: boolean;
  /** Whether to show the feedback buttons */
  showFeedback?: boolean;
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
  /** Current feedback state */
  feedback?: "up" | "down" | null;
  /** Callback when feedback is changed */
  onFeedback?: (feedback: "up" | "down" | null) => void;
  /** Message ID for localStorage key */
  messageId?: string;
  /** Session ID for feedback API calls */
  sessionId?: string;
  /** Feedback value from server (takes priority over localStorage) */
  messageFeedback?: "up" | "down" | null;
  /** Callback to fork the conversation from this message */
  onFork?: () => void;
}

function ActionBar({
  showCopy = true,
  showRetry = true,
  showDebug = true,
  showFeedback = true,
  content,
  onCopy,
  onRetry,
  onDebugToggle,
  isDebugActive = false,
  feedback: externalFeedback,
  onFeedback,
  messageId,
  sessionId,
  messageFeedback,
  onFork,
}: ActionBarProps) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const [internalFeedback, setInternalFeedback] = useState<"up" | "down" | null>(null);

  // Use external feedback if provided, otherwise use internal state
  const feedback = externalFeedback !== undefined ? externalFeedback : internalFeedback;

  // Load feedback from localStorage on mount
  const loadFeedbackFromStorage = useCallback(() => {
    if (!messageId) return null;
    try {
      const storageKey = `chat_feedback_${messageId}`;
      const stored = localStorage.getItem(storageKey);
      if (stored === "up" || stored === "down") {
        return stored;
      }
    } catch {
      // Silently fail if localStorage is not available
    }
    return null;
  }, [messageId]);

  // Initialize feedback from server value (takes priority) or localStorage on mount
  useEffect(() => {
    if (messageFeedback != null) {
      setInternalFeedback(messageFeedback);
      return;
    }
    const storedFeedback = loadFeedbackFromStorage();
    if (storedFeedback && externalFeedback === undefined) {
      setInternalFeedback(storedFeedback);
    }
  }, [messageId, messageFeedback, loadFeedbackFromStorage, externalFeedback]);

  // Save feedback to localStorage
  const saveFeedbackToStorage = useCallback((value: "up" | "down" | null) => {
    if (!messageId) return;
    try {
      const storageKey = `chat_feedback_${messageId}`;
      if (value === null) {
        localStorage.removeItem(storageKey);
      } else {
        localStorage.setItem(storageKey, value);
      }
    } catch {
      // Silently fail if localStorage is not available
    }
  }, [messageId]);

  const handleCopy = useCallback(async () => {
    const cleanContent = content
      .replace(/\[Source:[^\]]+\]/g, '')
      .replace(/\[S\d+\]/g, '')
      .trim();
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(cleanContent);
      } else {
        const ta = document.createElement('textarea');
        ta.value = cleanContent;
        ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (!ok) throw new Error('execCommand failed');
      }
      setCopied(true);
      onCopy?.();
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyFailed(true);
      toast.error("Couldn't copy to clipboard");
      setTimeout(() => setCopyFailed(false), 2000);
    }
  }, [content, onCopy]);

  const handleFeedback = useCallback((type: "up" | "down") => {
    // Toggle off if clicking the same feedback
    const previousFeedback = internalFeedback;
    const newFeedback = feedback === type ? null : type;

    if (externalFeedback === undefined) {
      setInternalFeedback(newFeedback);
    }

    saveFeedbackToStorage(newFeedback);
    onFeedback?.(newFeedback);

    if (sessionId && messageId && !isNaN(Number(messageId))) {
      updateMessageFeedback(Number(sessionId), Number(messageId), newFeedback)
        .catch(() => {
          // Revert optimistic update
          setInternalFeedback(previousFeedback);
          saveFeedbackToStorage(previousFeedback);
          onFeedback?.(previousFeedback);
          toast.error("Couldn't save feedback");
        });
    }
  }, [feedback, internalFeedback, externalFeedback, onFeedback, saveFeedbackToStorage, sessionId, messageId]);

  return (
    <div className="flex items-center gap-1 mt-3 opacity-60 group-hover:opacity-100 focus-within:opacity-100 [@media(pointer:coarse)]:opacity-100 transition-opacity duration-200">
      <TooltipProvider>
        {showCopy && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={handleCopy}
                aria-label={copied ? "Copied" : copyFailed ? "Copy failed" : "Copy message"}
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-success" />
                ) : copyFailed ? (
                  <AlertCircle className="h-3.5 w-3.5 text-destructive" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>{copied ? "Copied!" : copyFailed ? "Copy failed" : "Copy"}</p>
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

        {onFork && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onFork}
                aria-label="Branch conversation from here"
              >
                <GitBranch className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Branch from here</p>
            </TooltipContent>
          </Tooltip>
        )}

        {import.meta.env.DEV && showDebug && (
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

        {showFeedback && (
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className={cn("h-7 w-7 transition-all duration-150", feedback === "up" && "bg-accent text-accent-foreground scale-110")}
                  onClick={() => handleFeedback("up")}
                  aria-label="Good response"
                  aria-pressed={feedback === "up"}
                >
                  <ThumbsUp className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Good response</p>
              </TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className={cn("h-7 w-7 transition-all duration-150", feedback === "down" && "bg-accent text-accent-foreground scale-110")}
                  onClick={() => handleFeedback("down")}
                  aria-label="Bad response"
                  aria-pressed={feedback === "down"}
                >
                  <ThumbsDown className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Bad response</p>
              </TooltipContent>
            </Tooltip>
          </>
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
  showDebug,
  onSourceClick,
  onViewAllSources,
  onCopy,
  onRetry,
  onDebugToggle,
  feedback: externalFeedback,
  onFeedback,
  onFork,
  sessionId,
  messageFeedback,
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
  const renderedContent = useMemo(() => {
  const renderContent = () => {
    // TECH DEBT: This creates one ReactMarkdown + rehypeSanitize parse cycle per
    // text segment (N segments = N parse cycles for N citations). Fix: replace
    // citation markers with unique tokens before rendering, run a single markdown
    // pass, then post-process the output to swap tokens for React elements.
    return segments.map((segment, index) => {
      if (segment.type === "citation") {
        // Resolve by source_label first, then by filename (legacy), then by index
        const source =
          message.sources?.find((s) => s.source_label === segment.sourceName) ||
          message.sources?.find((s) => s.filename === segment.sourceName) ||
          (() => {
            // Try parsing S# label to get index
            const labelMatch = segment.sourceName.match(/^S(\d+)$/);
            if (labelMatch && message.sources) {
              const idx = parseInt(labelMatch[1], 10) - 1;
              return idx >= 0 && idx < message.sources.length ? message.sources[idx] : undefined;
            }
            return undefined;
          })();
        if (source) {
          // Index numbering matches the evidence strip / right pane, so the
          // inline pill's number points the reader to the same ordinal in
          // both detail views. Resolve via citedSources so duplicates reuse
          // the first occurrence's index.
          const sourceIndex = citedSources.findIndex((s) => s.id === source.id);
          const displayIndex = sourceIndex >= 0 ? sourceIndex : index;
          return (
            <CitationChip
              key={index}
              source={source}
              index={displayIndex}
              onClick={() => handleSourceClick(source)}
              variant="inline"
            />
          );
        }
        // If source not found, render as plain text
        return <span key={index}>[{segment.sourceName}]</span>;
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
            // Prevent double-wrapping: block code renders its own <pre>
            pre: ({ children }) => <>{children}</>,
            code: ({ className, children, ...props }) => {
              const isBlock = Boolean(className?.startsWith("language-"));
              if (!isBlock) {
                return (
                  <code
                    className="bg-muted px-1 py-0.5 rounded text-sm font-mono"
                    {...props}
                  >
                    {children}
                  </code>
                );
              }
              const language = className?.replace("language-", "") ?? "";
              const codeText = String(children).replace(/\n$/, "");
              return (
                <pre className="rounded-lg bg-muted p-4 overflow-x-auto text-sm font-mono my-3 relative group/code">
                  {language && (
                    <span className="absolute top-2 left-3 text-[10px] text-muted-foreground select-none">
                      {language}
                    </span>
                  )}
                  <CopyButton
                    text={codeText}
                    label="Copy code"
                    className="absolute top-1.5 right-1.5 opacity-0 group-hover/code:opacity-100 focus:opacity-100 transition-opacity"
                  />
                  <code className={className}>{children}</code>
                </pre>
              );
            },
          }}
        >
          {segment.content}
        </ReactMarkdown>
      );
    });
  };
  return renderContent();
  }, [segments, citedSources, message.sources, handleSourceClick]);

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
        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-primary/10 text-primary"
        aria-hidden="true"
      >
        <Bot className="h-4 w-4" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span className="font-semibold text-sm">Assistant</span>
        </div>

        {/* Message Body */}
        <div className="prose prose-sm dark:prose-invert max-w-none">
          {renderedContent}
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
          <div className="mt-3 flex items-start gap-2 rounded-md bg-destructive/10 border border-destructive/30 p-3">
            <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-destructive">Error</p>
              <p className="text-xs text-destructive/80 mt-0.5">{message.error}</p>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="mt-2 text-xs text-destructive-foreground underline hover:no-underline"
                >
                  Try again →
                </button>
              )}
            </div>
          </div>
        )}

        {/* Stopped State */}
        {message.stopped && !message.error && (
          <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-muted border border-border px-3 py-1.5">
            <span className="text-xs font-medium text-muted-foreground">Stopped</span>
          </div>
        )}

        {/* Action Bar */}
        {!isStreaming && (
          <ActionBar
            content={message.content}
            showDebug={showDebug}
            onCopy={onCopy}
            onRetry={onRetry}
            onDebugToggle={handleDebugToggle}
            isDebugActive={isDebugActive}
            feedback={externalFeedback}
            onFeedback={onFeedback}
            messageId={message.id}
            onFork={onFork}
            sessionId={sessionId}
            messageFeedback={messageFeedback}
          />
        )}

        {/* Debug Info */}
        {import.meta.env.DEV && isDebugActive && (
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
