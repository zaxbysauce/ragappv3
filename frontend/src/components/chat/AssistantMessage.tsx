// frontend/src/components/chat/AssistantMessage.tsx
import { useState, useMemo, useCallback } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Bot, AlertCircle } from "lucide-react";
import type { Message } from "@/stores/useChatStore";
import type { Source } from "@/lib/api";
import { useChatShellStore } from "@/stores/useChatShellStore";
import { MarkdownMessage, parseCitationSegments } from "./MarkdownMessage";
import { SourceCards } from "./SourceCards";
import { MemoryCards } from "./MemoryCards";
import { AssistantMessageActions } from "./MessageActions";

// Re-export for backwards compat with tests
export { parseCitationSegments as parseCitations };

interface AssistantMessageProps {
  message: Message;
  isStreaming?: boolean;
  showDebug?: boolean;
  onSourceClick?: (source: Source) => void;
  onViewAllSources?: () => void;
  onCopy?: () => void;
  onRetry?: () => void;
  onDebugToggle?: (isActive: boolean) => void;
  feedback?: "up" | "down" | null;
  onFeedback?: (feedback: "up" | "down" | null) => void;
  onFork?: () => void;
  sessionId?: string;
  messageFeedback?: "up" | "down" | null;
}

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
  const prefersReducedMotion = useReducedMotion();

  // Derive cited sources and memories for source/memory cards
  const { citedSources, citedMemories } = useMemo(
    () => parseCitationSegments(message.content, message.sources, message.memoriesUsed),
    [message.content, message.sources, message.memoriesUsed]
  );

  const handleSourceClick = useCallback(
    (source: Source) => {
      setSelectedEvidenceSource(source);
      setActiveRightTab("evidence");
      openRightPane();
      onSourceClick?.(source);
    },
    [setSelectedEvidenceSource, setActiveRightTab, openRightPane, onSourceClick]
  );

  const handleViewAll = useCallback(() => {
    setActiveRightTab("evidence");
    openRightPane();
    onViewAllSources?.();
  }, [setActiveRightTab, openRightPane, onViewAllSources]);

  const handleDebugToggle = useCallback(() => {
    const next = !isDebugActive;
    setIsDebugActive(next);
    onDebugToggle?.(next);
  }, [isDebugActive, onDebugToggle]);

  // Source cards: prefer cited sources, fall back to all sources
  const sourcesForCards = citedSources.length > 0 ? citedSources : (message.sources ?? []);
  // Memory cards: prefer cited memories, fall back to all memories.
  // Memories are always shown distinct from document sources.
  const memoriesForCards =
    citedMemories.length > 0 ? citedMemories : (message.memoriesUsed ?? []);

  return (
    <motion.div
      initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={{ duration: prefersReducedMotion ? 0.1 : 0.25 }}
      className="group flex gap-3 px-4 py-5"
      role="article"
      aria-label="Assistant message"
    >
      {/* Avatar */}
      <div
        className="flex-shrink-0 w-7 h-7 mt-0.5 rounded-full flex items-center justify-center bg-primary/10 text-primary"
        aria-hidden
      >
        <Bot className="h-3.5 w-3.5" />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 max-w-[68ch]">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Assistant</span>
        </div>

        {/* Markdown body */}
        <MarkdownMessage
          content={message.content}
          sources={message.sources}
          memories={message.memoriesUsed}
          isStreaming={isStreaming}
          onCitationClick={handleSourceClick}
          citedSources={citedSources}
        />

        {/* Source cards — shown below the message body */}
        {!isStreaming && sourcesForCards.length > 0 && (
          <SourceCards
            sources={sourcesForCards}
            onSourceClick={handleSourceClick}
            onViewAll={handleViewAll}
          />
        )}

        {/* Memory cards — distinct from document sources */}
        {!isStreaming && memoriesForCards.length > 0 && (
          <MemoryCards memories={memoriesForCards} />
        )}

        {/* Error */}
        {message.error && (
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3">
            <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" aria-hidden />
            <div className="min-w-0">
              <p className="text-sm font-medium text-destructive">Error</p>
              <p className="text-xs text-destructive/80 mt-0.5">{message.error}</p>
              {onRetry && (
                <button onClick={onRetry} className="mt-2 text-xs text-destructive underline hover:no-underline">
                  Try again →
                </button>
              )}
            </div>
          </div>
        )}

        {/* Stopped */}
        {message.stopped && !message.error && (
          <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-muted border border-border px-3 py-1.5">
            <span className="text-xs font-medium text-muted-foreground">Stopped</span>
          </div>
        )}

        {/* Action bar */}
        {!isStreaming && (
          <AssistantMessageActions
            content={message.content}
            onRetry={onRetry}
            onFork={onFork}
            onDebugToggle={handleDebugToggle}
            isDebugActive={isDebugActive}
            showDebug={showDebug}
            messageId={message.id}
            sessionId={sessionId}
            externalFeedback={externalFeedback}
            serverFeedback={messageFeedback}
            onFeedback={onFeedback}
            onCopy={onCopy}
          />
        )}

        {/* Debug panel */}
        {import.meta.env.DEV && isDebugActive && (
          <div className="mt-3 p-3 rounded-lg bg-muted border text-xs font-mono">
            <div className="text-muted-foreground mb-1">Debug Info:</div>
            <div>Message ID: {message.id}</div>
            <div>Sources: {message.sources?.length ?? 0}</div>
            <div>Cited: {citedSources.length}</div>
            <div>Length: {message.content.length} chars</div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export default AssistantMessage;
