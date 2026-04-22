import { motion } from "framer-motion";
import { User, Bot, AlertCircle, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";
import { MessageContent } from "./MessageContent";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Message } from "@/stores/useChatStore";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
  onFork?: () => void;
}

export function MessageBubble({ message, isStreaming, onFork }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "group flex gap-3 p-4",
        isUser ? "bg-primary/10" : "bg-muted/30"
      )}
    >
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
          isUser ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
        )}
      >
        {isUser ? (
          <User className="h-4 w-4" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-semibold text-sm">
            {isUser ? "You" : "Assistant"}
          </span>
        </div>

        <MessageContent
          content={message.content}
          sources={message.sources}
          isStreaming={isStreaming && !isUser}
        />

        {message.error && (
          <div className="mt-3 flex items-start gap-2 rounded-md bg-destructive/10 border border-destructive/30 p-3">
            <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-destructive">Error</p>
              <p className="text-xs text-destructive/80 mt-0.5">{message.error}</p>
            </div>
          </div>
        )}

        {message.stopped && !message.error && (
          <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-muted border border-border px-3 py-1.5">
            <span className="text-xs font-medium text-muted-foreground">Stopped</span>
          </div>
        )}

        {onFork && (
          <div className="flex items-center mt-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
            <TooltipProvider>
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
            </TooltipProvider>
          </div>
        )}
      </div>
    </motion.div>
  );
}
