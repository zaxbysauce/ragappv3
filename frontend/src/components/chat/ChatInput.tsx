import { useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatStore } from "@/stores/useChatStore";
import { cn } from "@/lib/utils";
import { MAX_INPUT_LENGTH } from "@/hooks/useSendMessage";

interface ChatInputProps {
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  className?: string;
}

export function ChatInput({ onSend, onStop, isStreaming, className }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { input, setInput, inputError } = useChatStore();

  const handleSubmit = async () => {
    if (!input.trim() || isStreaming) return;
    if (input.length > MAX_INPUT_LENGTH) return;
    onSend();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  };

  useEffect(() => {
    handleInput();
  }, []);

  return (
    <div className={cn("flex flex-col gap-2 p-4 border-t border-border", className)}>
      {inputError && (
        <div className="text-xs text-destructive" role="alert">{inputError}</div>
      )}
      <div className="flex items-end gap-2">
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message... (Enter to send, Shift+Enter for new line)"
          className="min-h-[44px] max-h-32 resize-none"
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={isStreaming}
        />
        {isStreaming ? (
          <Button variant="destructive" size="icon" onClick={onStop} aria-label="Stop generating">
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button size="icon" onClick={handleSubmit} disabled={!input.trim()} aria-label="Send message">
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
