import { useState, useCallback, useEffect } from "react";
import {
  Copy,
  Check,
  RotateCcw,
  Bug,
  ThumbsUp,
  ThumbsDown,
  AlertCircle,
  GitBranch,
  Pencil,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { updateMessageFeedback } from "@/lib/api";

// =============================================================================
// CopyButton with toast feedback
// =============================================================================

interface CopyActionProps {
  content: string;
  /** If true, strip [S1] / [Source:…] markers before copying */
  stripCitations?: boolean;
  onCopy?: () => void;
}

function CopyAction({ content, stripCitations = false, onCopy }: CopyActionProps) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");

  const handleCopy = useCallback(async () => {
    const text = stripCitations
      ? content.replace(/\[Source:[^\]]+\]/g, "").replace(/\[S\d+\]/g, "").trim()
      : content;
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.cssText = "position:fixed;opacity:0;pointer-events:none";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("execCommand failed");
      }
      setState("copied");
      onCopy?.();
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      toast.error("Couldn't copy to clipboard");
      setTimeout(() => setState("idle"), 2000);
    }
  }, [content, stripCitations, onCopy]);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 active:scale-95"
          onClick={handleCopy}
          aria-label={state === "copied" ? "Copied to clipboard" : state === "error" ? "Copy failed" : "Copy message"}
        >
          {state === "copied" ? (
            <Check className="h-3.5 w-3.5 text-success" />
          ) : state === "error" ? (
            <AlertCircle className="h-3.5 w-3.5 text-destructive" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        <p>{state === "copied" ? "Copied!" : state === "error" ? "Copy failed" : "Copy"}</p>
      </TooltipContent>
    </Tooltip>
  );
}

// =============================================================================
// FeedbackAction
// =============================================================================

interface FeedbackActionProps {
  messageId?: string;
  sessionId?: string;
  externalFeedback?: "up" | "down" | null;
  serverFeedback?: "up" | "down" | null;
  onFeedback?: (feedback: "up" | "down" | null) => void;
}

function FeedbackActions({
  messageId,
  sessionId,
  externalFeedback,
  serverFeedback,
  onFeedback,
}: FeedbackActionProps) {
  const [internalFeedback, setInternalFeedback] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    if (serverFeedback != null) {
      setInternalFeedback(serverFeedback);
      return;
    }
    if (!messageId) return;
    try {
      const stored = localStorage.getItem(`chat_feedback_${messageId}`);
      if (stored === "up" || stored === "down") setInternalFeedback(stored);
    } catch { /* ignore */ }
  }, [messageId, serverFeedback]);

  const current = externalFeedback !== undefined ? externalFeedback : internalFeedback;

  const handleFeedback = useCallback(
    (type: "up" | "down") => {
      const prev = internalFeedback;
      const next: "up" | "down" | null = current === type ? null : type;

      if (externalFeedback === undefined) setInternalFeedback(next);

      try {
        if (messageId) {
          if (next === null) {
            localStorage.removeItem(`chat_feedback_${messageId}`);
          } else {
            localStorage.setItem(`chat_feedback_${messageId}`, next);
          }
        }
      } catch { /* ignore */ }

      onFeedback?.(next);

      if (sessionId && messageId && !isNaN(Number(messageId))) {
        updateMessageFeedback(Number(sessionId), Number(messageId), next).catch(() => {
          if (externalFeedback === undefined) setInternalFeedback(prev);
          try {
            if (messageId) {
              if (prev === null) localStorage.removeItem(`chat_feedback_${messageId}`);
              else localStorage.setItem(`chat_feedback_${messageId}`, prev);
            }
          } catch { /* ignore */ }
          onFeedback?.(prev);
          toast.error("Couldn't save feedback");
        });
      }
    },
    [current, internalFeedback, externalFeedback, messageId, sessionId, onFeedback]
  );

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "h-7 w-7 transition-all duration-150 active:scale-95",
              current === "up" && "bg-accent text-accent-foreground scale-105"
            )}
            onClick={() => handleFeedback("up")}
            aria-label="Good response"
            aria-pressed={current === "up"}
          >
            <ThumbsUp className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent><p>Good response</p></TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "h-7 w-7 transition-all duration-150 active:scale-95",
              current === "down" && "bg-accent text-accent-foreground scale-105"
            )}
            onClick={() => handleFeedback("down")}
            aria-label="Bad response"
            aria-pressed={current === "down"}
          >
            <ThumbsDown className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent><p>Bad response</p></TooltipContent>
      </Tooltip>
    </>
  );
}

// =============================================================================
// AssistantMessageActions
// =============================================================================

interface AssistantMessageActionsProps {
  content: string;
  onRetry?: () => void;
  onFork?: () => void;
  onDebugToggle?: () => void;
  isDebugActive?: boolean;
  showDebug?: boolean;
  messageId?: string;
  sessionId?: string;
  externalFeedback?: "up" | "down" | null;
  serverFeedback?: "up" | "down" | null;
  onFeedback?: (feedback: "up" | "down" | null) => void;
  onCopy?: () => void;
}

export function AssistantMessageActions({
  content,
  onRetry,
  onFork,
  onDebugToggle,
  isDebugActive = false,
  showDebug = true,
  messageId,
  sessionId,
  externalFeedback,
  serverFeedback,
  onFeedback,
  onCopy,
}: AssistantMessageActionsProps) {
  return (
    <div className="flex items-center gap-0.5 mt-3 opacity-60 group-hover:opacity-100 focus-within:opacity-100 [@media(pointer:coarse)]:opacity-100 transition-opacity duration-200">
      <TooltipProvider>
        <CopyAction content={content} stripCitations onCopy={onCopy} />

        {onRetry && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 active:scale-95"
                onClick={onRetry}
                aria-label="Retry"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent><p>Regenerate</p></TooltipContent>
          </Tooltip>
        )}

        {onFork && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 active:scale-95"
                onClick={onFork}
                aria-label="Branch conversation from here"
              >
                <GitBranch className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent><p>Branch from here</p></TooltipContent>
          </Tooltip>
        )}

        {import.meta.env.DEV && showDebug && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className={cn("h-7 w-7 active:scale-95", isDebugActive && "bg-accent text-accent-foreground")}
                onClick={onDebugToggle}
                aria-label="Toggle debug info"
              >
                <Bug className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent><p>Debug</p></TooltipContent>
          </Tooltip>
        )}

        <FeedbackActions
          messageId={messageId}
          sessionId={sessionId}
          externalFeedback={externalFeedback}
          serverFeedback={serverFeedback}
          onFeedback={onFeedback}
        />
      </TooltipProvider>
    </div>
  );
}

// =============================================================================
// UserMessageActions
// =============================================================================

interface UserMessageActionsProps {
  content: string;
  onEdit?: () => void;
  isEditDisabled?: boolean;
  onFork?: () => void;
}

export function UserMessageActions({
  content,
  onEdit,
  isEditDisabled = false,
  onFork,
}: UserMessageActionsProps) {
  return (
    <div className="flex items-center gap-0.5 mt-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 [@media(pointer:coarse)]:opacity-100 transition-opacity duration-200">
      <TooltipProvider>
        <CopyAction content={content} />

        {onEdit && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 active:scale-95"
                onClick={onEdit}
                disabled={isEditDisabled}
                aria-label="Edit message"
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent><p>{isEditDisabled ? "Editing disabled while generating" : "Edit"}</p></TooltipContent>
          </Tooltip>
        )}

        {onFork && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 active:scale-95"
                onClick={onFork}
                aria-label="Branch conversation from here"
              >
                <GitBranch className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent><p>Branch from here</p></TooltipContent>
          </Tooltip>
        )}
      </TooltipProvider>
    </div>
  );
}
