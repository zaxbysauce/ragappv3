// frontend/src/components/chat/TranscriptPane.tsx

import { useRef, useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Square,
  Paperclip,
  Slash,
  Sparkles,
  Database,
  ChevronDown,
  ArrowDown,
  FileText,
  GitCompare,
  Calendar,
  ListChecks,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { MessageBubble } from "./MessageBubble";
import { AssistantMessage } from "./AssistantMessage";
import { useChatStore } from "@/stores/useChatStore";
import { useVaultStore } from "@/stores/useVaultStore";
import { useSendMessage, MAX_INPUT_LENGTH } from "@/hooks/useSendMessage";
import { useChatHistory } from "@/hooks/useChatHistory";

// =============================================================================
// TYPES & INTERFACES
// =============================================================================

interface TranscriptPaneProps {
  /** Optional className for styling overrides */
  className?: string;
}

interface ComposerProps {
  /** Callback when user sends a message */
  onSend: () => void;
  /** Callback when user stops streaming */
  onStop: () => void;
  /** Whether a response is currently streaming */
  isStreaming: boolean;
  /** Optional className for styling overrides */
  className?: string;
  /** Ref to the textarea for external focus control */
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
}

interface EmptyTranscriptProps {
  /** Callback when user clicks a suggested prompt */
  onPromptClick: (prompt: string) => void;
  /** Whether the active vault has indexed documents */
  hasIndexedDocs: boolean;
  /** Callback to navigate to documents page */
  onNavigateToDocuments?: () => void;
}

interface SlashCommand {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
}

// =============================================================================
// CONSTANTS
// =============================================================================

const SLASH_COMMANDS: SlashCommand[] = [
  {
    id: "summarize",
    label: "/summarize",
    description: "Summarize this document",
    icon: <FileText className="h-4 w-4" />,
  },
  {
    id: "compare",
    label: "/compare",
    description: "Compare these sources",
    icon: <GitCompare className="h-4 w-4" />,
  },
  {
    id: "timeline",
    label: "/timeline",
    description: "Create a timeline",
    icon: <Calendar className="h-4 w-4" />,
  },
  {
    id: "actions",
    label: "/actions",
    description: "List action items",
    icon: <ListChecks className="h-4 w-4" />,
  },
];

const SUGGESTED_PROMPTS = [
  "What are the key findings?",
  "Summarize the main topics",
  "What data sources were used?",
  "What are the main conclusions?",
];

// =============================================================================
// COMPONENT: EmptyTranscript
// =============================================================================

function EmptyTranscript({
  onPromptClick,
  hasIndexedDocs,
  onNavigateToDocuments,
}: EmptyTranscriptProps) {
  return (
    <div
      className="flex h-full flex-col items-center justify-center px-4 py-12"
      role="region"
      aria-label="Empty transcript"
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex max-w-md flex-col items-center text-center"
      >
        {/* App branding icon */}
        <div
          className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10"
          aria-hidden="true"
        >
          <Sparkles className="h-8 w-8 text-primary" />
        </div>

        <h2 className="mb-2 text-xl font-semibold text-foreground">
          {hasIndexedDocs ? "What would you like to know?" : "Upload documents to get started"}
        </h2>

        <p className="mb-8 text-sm text-muted-foreground">
          {hasIndexedDocs
            ? "Select a prompt below or type your own question to explore your documents."
            : "Add documents to your vault to start chatting with your knowledge base."}
        </p>

        {hasIndexedDocs ? (
          // Suggested prompts grid
          <div
            className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2"
            role="list"
            aria-label="Suggested prompts"
          >
            {SUGGESTED_PROMPTS.map((prompt, index) => (
              <button
                key={index}
                onClick={() => onPromptClick(prompt)}
                className="group flex items-start gap-3 rounded-lg border border-border bg-card p-4 text-left transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label={`Use prompt: ${prompt}`}
              >
                <Sparkles
                  className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground group-hover:text-accent-foreground"
                  aria-hidden="true"
                />
                <span className="text-sm">{prompt}</span>
              </button>
            ))}
          </div>
        ) : (
          // Empty vault CTA
          <Button
            onClick={onNavigateToDocuments}
            className="gap-2"
            aria-label="Go to documents page to upload files"
          >
            <Database className="h-4 w-4" aria-hidden="true" />
            Go to Documents
          </Button>
        )}
      </motion.div>
    </div>
  );
}

// =============================================================================
// COMPONENT: Composer
// =============================================================================

function Composer({ onSend, onStop, isStreaming, className, inputRef }: ComposerProps) {
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const textareaRef = inputRef || internalRef;
  const { input, setInput, inputError } = useChatStore();
  const { getActiveVault } = useVaultStore();
  const activeVault = getActiveVault();

  // Slash command menu state
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const [slashQuery, setSlashQuery] = useState("");

  // Filter commands based on query
  const filteredCommands = SLASH_COMMANDS.filter((cmd) =>
    cmd.label.toLowerCase().includes(slashQuery.toLowerCase())
  );

  // Auto-grow textarea
  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      const newHeight = Math.min(textarea.scrollHeight, 200); // ~8 lines max
      textarea.style.height = `${Math.max(44, newHeight)}px`;
    }
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [input, adjustTextareaHeight]);

  // Handle input changes
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // Check for slash command trigger
    const lines = value.split("\n");
    const lastLine = lines[lines.length - 1];

    if (lastLine.startsWith("/") && !lastLine.includes(" ")) {
      setShowSlashMenu(true);
      setSlashQuery(lastLine.slice(1));
      setSelectedCommandIndex(0);
    } else {
      setShowSlashMenu(false);
      setSlashQuery("");
    }
  };

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashMenu) {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedCommandIndex((prev) =>
            prev < filteredCommands.length - 1 ? prev + 1 : prev
          );
          return;
        case "ArrowUp":
          e.preventDefault();
          setSelectedCommandIndex((prev) => (prev > 0 ? prev - 1 : 0));
          return;
        case "Enter":
          e.preventDefault();
          if (filteredCommands[selectedCommandIndex]) {
            insertCommand(filteredCommands[selectedCommandIndex]);
          }
          return;
        case "Escape":
          e.preventDefault();
          setShowSlashMenu(false);
          return;
      }
    }

    // Enter to send, Shift+Enter for new line
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Insert selected command
  const insertCommand = (command: SlashCommand) => {
    const lines = input.split("\n");
    lines[lines.length - 1] = command.label + " ";
    setInput(lines.join("\n"));
    setShowSlashMenu(false);
    textareaRef.current?.focus();
  };

  // Handle submit
  const handleSubmit = () => {
    if (!input.trim() || isStreaming) return;
    if (input.length > MAX_INPUT_LENGTH) return;
    onSend();
  };

  return (
    <div className={cn("relative", className)}>
      {/* Vault Context Pill */}
      {activeVault && (
        <div className="mb-2 flex items-center gap-2">
          <Badge
            variant="secondary"
            className="gap-1.5 text-xs font-normal"
            aria-label={`Active vault: ${activeVault.name}`}
          >
            <Database className="h-3 w-3" aria-hidden="true" />
            {activeVault.name}
            <ChevronDown className="h-3 w-3 opacity-50" aria-hidden="true" />
          </Badge>
        </div>
      )}

      {/* Composer container */}
      <div className="relative rounded-xl border border-input bg-background shadow-sm">
        {/* Textarea */}
        <Textarea
          ref={textareaRef as React.Ref<HTMLTextAreaElement>}
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder="Message... (type / for commands, Enter to send, Shift+Enter for new line)"
          className="min-h-[44px] max-h-[200px] resize-none border-0 bg-transparent px-4 py-3 text-sm placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
          disabled={isStreaming}
          aria-label="Message input"
          aria-describedby={inputError ? "input-error" : undefined}
          aria-expanded={showSlashMenu}
          aria-haspopup="listbox"
          aria-controls={showSlashMenu ? "slash-command-menu" : undefined}
          rows={1}
        />

        {/* Slash command menu */}
        <AnimatePresence>
          {showSlashMenu && filteredCommands.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
              id="slash-command-menu"
              role="listbox"
              aria-label="Slash commands"
              className="absolute bottom-full left-0 z-50 mb-2 w-72 overflow-hidden rounded-lg border border-border bg-popover shadow-lg"
            >
              <div className="max-h-64 overflow-y-auto py-1">
                {filteredCommands.map((command, index) => (
                  <button
                    key={command.id}
                    onClick={() => insertCommand(command)}
                    onMouseEnter={() => setSelectedCommandIndex(index)}
                    role="option"
                    aria-selected={index === selectedCommandIndex}
                    className={cn(
                      "flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors",
                      index === selectedCommandIndex
                        ? "bg-accent text-accent-foreground"
                        : "text-popover-foreground hover:bg-accent/50"
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-md",
                        index === selectedCommandIndex
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground"
                      )}
                    >
                      {command.icon}
                    </span>
                    <div className="flex flex-col">
                      <span className="font-medium">{command.label}</span>
                      <span
                        className={cn(
                          "text-xs",
                          index === selectedCommandIndex
                            ? "text-accent-foreground/70"
                            : "text-muted-foreground"
                        )}
                      >
                        {command.description}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error message */}
        {inputError && (
          <div id="input-error" role="alert" className="px-4 pb-2 text-xs text-destructive">
            {inputError}
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center justify-between border-t border-border px-2 py-2">
          <div className="flex items-center gap-1">
            {/* Attachment button (disabled) */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground"
                    disabled
                    aria-label="Attach file (coming soon)"
                  >
                    <Paperclip className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Coming soon</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Slash command hint */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground"
                    onClick={() => {
                      const currentInput = useChatStore.getState().input;
                      setInput(currentInput + "/");
                      textareaRef.current?.focus();
                    }}
                    aria-label="Open slash commands"
                  >
                    <Slash className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Slash commands</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          {/* Send/Stop button */}
          {isStreaming ? (
            <Button
              variant="destructive"
              size="sm"
              onClick={onStop}
              className="gap-1.5"
              aria-label="Stop generating"
            >
              <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
              Stop
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={!input.trim() || input.length > MAX_INPUT_LENGTH}
              className="gap-1.5"
              aria-label="Send message"
            >
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
              Send
            </Button>
          )}
        </div>
      </div>

      {/* Character count warning */}
      {input.length > MAX_INPUT_LENGTH * 0.8 && (
        <div
          className={cn(
            "mt-1 text-right text-xs",
            input.length > MAX_INPUT_LENGTH ? "text-destructive" : "text-muted-foreground"
          )}
          aria-live="polite"
        >
          {input.length}/{MAX_INPUT_LENGTH}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// COMPONENT: TranscriptPane
// =============================================================================

export function TranscriptPane({ className }: TranscriptPaneProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();
  const { messages, isStreaming, setInput } = useChatStore();
  const { getActiveVault } = useVaultStore();
  const activeVault = getActiveVault();
  const vaultId = useVaultStore((state) => state.activeVaultId);

  // Use chat history hook for refresh functionality
  const { refreshHistory } = useChatHistory(vaultId);
  const { handleSend, handleStop } = useSendMessage(vaultId, refreshHistory);

  // Scroll state
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);

  // Check if vault has indexed documents (using file_count from Vault interface)
  const hasIndexedDocs = activeVault ? activeVault.file_count > 0 : false;

  // Auto-scroll to bottom on new messages only if user is already at bottom
  useEffect(() => {
    if (isAtBottom && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming, isAtBottom]);

  // Handle scroll events - track if user is near bottom (<100px)
  const handleScroll = () => {
    const container = scrollRef.current;
    if (!container) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const atBottom = distanceFromBottom < 100;

    setIsAtBottom(atBottom);
    setShowScrollButton(!atBottom);
  };

  // Scroll to bottom
  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      setIsAtBottom(true);
      setShowScrollButton(false);
    }
  };

  // Handle suggested prompt click - sets input and focuses composer
  const handlePromptClick = (prompt: string) => {
    setInput(prompt);
    // Focus the composer textarea after a brief delay to ensure state update
    setTimeout(() => {
      composerRef.current?.focus();
    }, 0);
  };

  // Handle navigation to documents page
  const handleNavigateToDocuments = () => {
    navigate('/documents');
  };

  return (
    <div className={cn("flex h-full flex-col", className)}>
      {/* Message list area */}
      <div className="relative flex-1 overflow-hidden">
        <ScrollArea
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-full"
          aria-label="Chat messages"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
        >
          <div className="mx-auto max-w-4xl">
            {messages.length === 0 ? (
              <EmptyTranscript
                onPromptClick={handlePromptClick}
                hasIndexedDocs={hasIndexedDocs}
                onNavigateToDocuments={handleNavigateToDocuments}
              />
            ) : (
              <div className="flex flex-col">
                {messages.map((message, index) => {
                  const isLastMessage = index === messages.length - 1;
                  const isAssistantStreaming = isStreaming && isLastMessage && message.role === "assistant";

                  if (message.role === "assistant") {
                    return (
                      <AssistantMessage
                        key={message.id}
                        message={message}
                        isStreaming={isAssistantStreaming}
                        onCopy={() => { navigator.clipboard.writeText(message.content); }}
                        onRetry={() => { /* TODO: retry logic - UI only for now */ }}
                        onDebugToggle={() => { /* TODO: toggle debug info */ }}
                      />
                    );
                  }

                  return (
                    <MessageBubble
                      key={message.id}
                      message={message}
                      isStreaming={isAssistantStreaming}
                    />
                  );
                })}
                {/* Spacer for bottom padding */}
                <div className="h-4" aria-hidden="true" />
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Scroll to bottom button */}
        <AnimatePresence>
          {showScrollButton && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ duration: 0.15 }}
              className="absolute bottom-4 left-1/2 -translate-x-1/2"
            >
              <Button
                variant="secondary"
                size="sm"
                onClick={scrollToBottom}
                className="h-8 gap-1.5 rounded-full px-3 shadow-lg"
                aria-label="Scroll to bottom"
              >
                <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                <span className="text-xs">New messages</span>
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Composer area */}
      <div className="border-t border-border bg-background p-4">
        <div className="mx-auto max-w-4xl">
          <Composer onSend={handleSend} onStop={handleStop} isStreaming={isStreaming} inputRef={composerRef} />
        </div>
      </div>
    </div>
  );
}

// Export individual components for flexibility
export { Composer, EmptyTranscript };
export type { TranscriptPaneProps, ComposerProps, EmptyTranscriptProps };
