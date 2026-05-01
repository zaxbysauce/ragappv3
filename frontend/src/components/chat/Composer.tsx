// Composer — extracted from TranscriptPane for maintainability.
// Handles draft persistence, auto-grow, slash commands, IME guard, file attachments.

import { useRef, useEffect, useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import {
  Send,
  Square,
  Slash,
  Database,
  FileText,
  GitCompare,
  Calendar,
  ListChecks,
  Paperclip,
  X,
  AlertCircle,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/stores/useChatStore";
import { useVaultStore } from "@/stores/useVaultStore";
import { uploadDocument } from "@/lib/api";
import { MAX_INPUT_LENGTH } from "@/hooks/useSendMessage";
import { toast } from "sonner";

// =============================================================================
// Types
// =============================================================================

interface SlashCommand {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
}

interface PendingAttachment {
  id: string;
  file: File;
  progress: number;
  status: "uploading" | "done" | "error";
  error?: string;
}

interface ComposerProps {
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  className?: string;
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
}

// =============================================================================
// Constants
// =============================================================================

const SLASH_COMMANDS: SlashCommand[] = [
  { id: "summarize", label: "/summarize", description: "Summarize this document", icon: <FileText className="h-4 w-4" /> },
  { id: "compare",   label: "/compare",   description: "Compare these sources",   icon: <GitCompare className="h-4 w-4" /> },
  { id: "timeline",  label: "/timeline",  description: "Create a timeline",        icon: <Calendar className="h-4 w-4" /> },
  { id: "actions",   label: "/actions",   description: "List action items",        icon: <ListChecks className="h-4 w-4" /> },
];

const DRAFT_PREFIX = "ragapp_chat_draft_";
const getDraftKey = (sessionId: string | null) => `${DRAFT_PREFIX}${sessionId ?? "new"}`;

// =============================================================================
// Composer
// =============================================================================

export function Composer({ onSend, onStop, isStreaming, className, inputRef }: ComposerProps) {
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const textareaRef = (inputRef ?? internalRef) as React.RefObject<HTMLTextAreaElement>;

  const { input, setInput, inputError, activeChatId } = useChatStore();
  const { getActiveVault } = useVaultStore();
  const activeVault = getActiveVault();
  const activeVaultId = useVaultStore((s) => s.activeVaultId);

  // Slash command menu
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [selectedCmd, setSelectedCmd] = useState(0);
  const [slashQuery, setSlashQuery] = useState("");

  // File attachments
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);

  // Draft — restore on session change, write on input changes
  const lastLoadedRef = useRef<string | null>(null);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const key = activeChatId ?? "new";
    if (lastLoadedRef.current === key) return;
    lastLoadedRef.current = key;
    try {
      setInput(localStorage.getItem(getDraftKey(activeChatId)) ?? "");
    } catch { /* private mode */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId]);

  const persistDraft = useCallback((value: string) => {
    if (typeof window === "undefined") return;
    try {
      const k = getDraftKey(activeChatId);
      if (value) localStorage.setItem(k, value);
      else localStorage.removeItem(k);
    } catch { /* ignore */ }
  }, [activeChatId]);

  // Auto-grow
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(44, Math.min(el.scrollHeight, 200))}px`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { adjustHeight(); }, [input, adjustHeight]);

  // Filtered slash commands
  const filteredCmds = SLASH_COMMANDS.filter((c) =>
    c.label.toLowerCase().includes(slashQuery.toLowerCase())
  );

  const insertCommand = useCallback((cmd: SlashCommand) => {
    const lines = input.split("\n");
    lines[lines.length - 1] = cmd.label + " ";
    const next = lines.join("\n");
    setInput(next);
    persistDraft(next);
    setShowSlashMenu(false);
    textareaRef.current?.focus();
  }, [input, setInput, persistDraft, textareaRef]);

  // Input change
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);
    persistDraft(value);

    const lines = value.split("\n");
    const last = lines[lines.length - 1];
    if (last.startsWith("/") && !last.includes(" ")) {
      setShowSlashMenu(true);
      setSlashQuery(last.slice(1));
      setSelectedCmd(0);
    } else {
      setShowSlashMenu(false);
      setSlashQuery("");
    }
  };

  // Keyboard handler with IME guard
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashMenu) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSelectedCmd((p) => Math.min(p + 1, filteredCmds.length - 1)); return; }
      if (e.key === "ArrowUp")   { e.preventDefault(); setSelectedCmd((p) => Math.max(p - 1, 0)); return; }
      if (e.key === "Enter")     { e.preventDefault(); if (filteredCmds[selectedCmd]) insertCommand(filteredCmds[selectedCmd]); return; }
      if (e.key === "Escape")    { e.preventDefault(); setShowSlashMenu(false); return; }
    }
    // IME guard: nativeEvent.isComposing is true while CJK composition is in progress
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!input.trim() || isStreaming || input.length > MAX_INPUT_LENGTH) return;
    if (attachments.some((a) => a.status === "uploading")) {
      toast.error("Please wait for file uploads to complete.");
      return;
    }
    persistDraft("");
    onSend();
    setAttachments([]);
  };

  // =============================================================================
  // File upload
  // =============================================================================

  const uploadFile = useCallback(async (file: File) => {
    if (!activeVaultId) {
      toast.error("No active vault. Please select a vault before uploading files.", { description: "Go to Documents to manage vaults." });
      return;
    }

    const id = `${Date.now()}-${Math.random()}`;
    const pending: PendingAttachment = { id, file, progress: 0, status: "uploading" };
    setAttachments((prev) => [...prev, pending]);

    try {
      await uploadDocument(
        file,
        (progress) => {
          setAttachments((prev) =>
            prev.map((a) => (a.id === id ? { ...a, progress } : a))
          );
        },
        activeVaultId
      );
      setAttachments((prev) =>
        prev.map((a) => (a.id === id ? { ...a, status: "done", progress: 100 } : a))
      );
      toast.success(`${file.name} uploaded to ${activeVault?.name ?? "vault"}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setAttachments((prev) =>
        prev.map((a) => (a.id === id ? { ...a, status: "error", error: msg } : a))
      );
      toast.error(`Failed to upload ${file.name}`, { description: msg });
    }
  }, [activeVaultId, activeVault]);

  const { getRootProps, getInputProps, isDragActive, open: openFilePicker } = useDropzone({
    noClick: true,
    noKeyboard: true,
    onDrop: (files) => files.forEach(uploadFile),
  });

  // Handle paste with files
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files);
    if (files.length > 0) {
      e.preventDefault();
      files.forEach(uploadFile);
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const hasUploading = attachments.some((a) => a.status === "uploading");

  // =============================================================================
  // Render
  // =============================================================================

  return (
    <TooltipProvider>
      <div className={cn("relative", className)} {...getRootProps()}>
        {/* Drag overlay */}
        {isDragActive && (
          <div className="absolute inset-0 z-20 flex items-center justify-center rounded-xl border-2 border-dashed border-primary bg-primary/5">
            <p className="text-sm font-medium text-primary">Drop files to upload</p>
          </div>
        )}

        {/* Vault context pill */}
        {activeVault && (
          <div className="mb-2 flex items-center gap-2">
            <Badge variant="secondary" className="gap-1.5 text-xs font-normal" aria-label={`Active vault: ${activeVault.name}`}>
              <Database className="h-3 w-3" aria-hidden />
              {activeVault.name}
            </Badge>
          </div>
        )}

        <span id="composer-help" className="sr-only">
          Press Enter to send, Shift+Enter for a new line, slash for commands, or paste/drop files to upload.
        </span>

        {/* Attachment tray */}
        {attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {attachments.map((att) => (
              <div
                key={att.id}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-2 py-1.5 text-xs",
                  att.status === "error"   && "border-destructive/50 bg-destructive/5",
                  att.status === "done"    && "border-success/50 bg-success/5",
                  att.status === "uploading" && "border-border bg-muted/50"
                )}
              >
                {att.status === "error" ? (
                  <AlertCircle className="h-3.5 w-3.5 text-destructive flex-shrink-0" />
                ) : (
                  <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                )}
                <span className="max-w-[120px] truncate">{att.file.name}</span>
                {att.status === "uploading" && (
                  <Progress value={att.progress} className="h-1 w-16" />
                )}
                {att.status === "error" && att.error && (
                  <span className="text-destructive">{att.error}</span>
                )}
                <button
                  onClick={() => removeAttachment(att.id)}
                  className="ml-1 text-muted-foreground hover:text-foreground"
                  aria-label={`Remove ${att.file.name}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Composer container */}
        <div
          className={cn(
            "relative rounded-xl border bg-card shadow-sm transition-all duration-150",
            "focus-within:border-primary/50 focus-within:shadow-md focus-within:shadow-primary/5",
            isStreaming ? "border-primary/30" : "border-input",
          )}
        >
          {/* Textarea — readOnly during streaming but still scrollable and accessible */}
          <Textarea
            ref={textareaRef as React.Ref<HTMLTextAreaElement>}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={isStreaming ? "Generating..." : "Message... (Enter to send · Shift+Enter for newline · / for commands)"}
            className={cn(
              "min-h-[44px] max-h-[200px] resize-none border-0 bg-transparent px-4 py-3",
              "text-sm placeholder:text-muted-foreground/60",
              "focus-visible:ring-0 focus-visible:ring-offset-0",
            )}
            readOnly={isStreaming}
            aria-label="Message input"
            aria-describedby={inputError ? "input-error composer-help" : "composer-help"}
            role="combobox"
            aria-expanded={showSlashMenu}
            aria-haspopup="listbox"
            aria-controls={showSlashMenu ? "slash-menu" : undefined}
            rows={1}
          />

          {/* Slash command menu */}
          <AnimatePresence>
            {showSlashMenu && (
              <motion.div
                id="slash-menu"
                role="listbox"
                aria-label="Slash commands"
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.12 }}
                className="absolute bottom-full left-0 z-50 mb-2 w-72 overflow-hidden rounded-lg border border-border bg-popover shadow-lg"
              >
                <div className="max-h-64 overflow-y-auto py-1">
                  {filteredCmds.length === 0 ? (
                    <div className="px-3 py-4 text-center text-sm text-muted-foreground">No matching commands</div>
                  ) : (
                    filteredCmds.map((cmd, i) => (
                      <button
                        key={cmd.id}
                        onClick={() => insertCommand(cmd)}
                        onMouseEnter={() => setSelectedCmd(i)}
                        role="option"
                        aria-selected={i === selectedCmd}
                        className={cn(
                          "flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors",
                          i === selectedCmd ? "bg-accent text-accent-foreground" : "text-popover-foreground hover:bg-accent/50"
                        )}
                      >
                        <span className={cn("flex h-8 w-8 items-center justify-center rounded-md", i === selectedCmd ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
                          {cmd.icon}
                        </span>
                        <div>
                          <div className="font-medium">{cmd.label}</div>
                          <div className={cn("text-xs", i === selectedCmd ? "text-accent-foreground/70" : "text-muted-foreground")}>{cmd.description}</div>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Validation error */}
          {inputError && (
            <div id="input-error" role="alert" className="px-4 pb-2 text-xs text-destructive">
              {inputError}
            </div>
          )}

          {/* Toolbar */}
          <div className="flex items-center justify-between border-t border-border px-2 py-2">
            <div className="flex items-center gap-1">
              {/* Slash command hint */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground active:scale-95"
                    onClick={() => { setInput(input + "/"); textareaRef.current?.focus(); }}
                    aria-label="Open slash commands"
                    tabIndex={-1}
                  >
                    <Slash className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent><p>Slash commands</p></TooltipContent>
              </Tooltip>

              {/* Attachment button */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground active:scale-95"
                    onClick={openFilePicker}
                    aria-label="Attach file"
                    tabIndex={-1}
                    disabled={isStreaming}
                  >
                    <Paperclip className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent><p>Attach file</p></TooltipContent>
              </Tooltip>
              {/* Hidden dropzone input */}
              <input {...getInputProps()} />
            </div>

            {/* Generation status label */}
            {isStreaming && (
              <span className="text-xs text-muted-foreground animate-pulse select-none">
                Generating…
              </span>
            )}

            {/* Send / Stop */}
            {isStreaming ? (
              <Button
                variant="destructive"
                size="sm"
                onClick={onStop}
                className="gap-1.5 h-8 active:scale-95"
                aria-label="Stop generating"
              >
                <Square className="h-3 w-3 fill-current" />
                Stop
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={handleSubmit}
                disabled={!input.trim() || input.length > MAX_INPUT_LENGTH || hasUploading}
                className="h-8 w-8 rounded-full p-0 shadow-sm active:scale-95"
                aria-label="Send message"
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>

        {/* Character count */}
        {input.length > MAX_INPUT_LENGTH * 0.75 && (
          <div
            className={cn(
              "mt-1 text-right text-[11px]",
              input.length > MAX_INPUT_LENGTH ? "text-destructive" : "text-muted-foreground"
            )}
            aria-live="polite"
          >
            {input.length}/{MAX_INPUT_LENGTH}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
