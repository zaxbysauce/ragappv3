import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { useChatStore } from "@/stores/useChatStore";
import { useSendMessage } from "@/hooks/useSendMessage";
import { Button } from "@/components/ui/button";
import { Plus, PanelLeftClose, PanelLeft, Download } from "lucide-react";
import { VaultSelector } from "@/components/vault/VaultSelector";
import { useVaultStore } from "@/stores/useVaultStore";
import { useChatHistory } from "@/hooks/useChatHistory";
import { cn } from "@/lib/utils";

interface ChatMessagesProps {
  toggleCanvasCollapse: () => void;
  canvasCollapsed: boolean;
}

export function ChatMessages({ toggleCanvasCollapse, canvasCollapsed }: ChatMessagesProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { messages, isStreaming, newChat } = useChatStore();
  const { activeVaultId } = useVaultStore();
  const { refreshHistory } = useChatHistory(activeVaultId);
  const { handleSend, handleStop } = useSendMessage(activeVaultId, refreshHistory);

  const handleExportChat = () => {
    const chatText = messages.map(m => {
      const role = m.role === "user" ? "User" : "Assistant";
      return `${role}: ${m.content}`;
    }).join("\n\n");

    const blob = new Blob([chatText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);

    // Safer blob handling without direct DOM manipulation
    try {
      const link = document.createElement("a");
      link.href = url;
      link.download = `chat-${new Date().toISOString().slice(0, 10)}.txt`;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();

      // Clean up after a short delay to allow the download to start
      setTimeout(() => {
        if (document.body.contains(link)) {
          document.body.removeChild(link);
        }
        URL.revokeObjectURL(url);
      }, 100);
    } catch (error) {
      console.error("Failed to export chat:", error);
      URL.revokeObjectURL(url);
    }
  };

  // H-5 fix: Only auto-scroll when user is near the bottom (within 150px)
  // so reading history isn't yanked away on every streaming token.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  return (
    <div className={cn("flex flex-col h-screen bg-background", canvasCollapsed ? "" : "pe-0")}>
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={newChat}>
            <Plus className="h-4 w-4" />
          </Button>
          <VaultSelector />
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={handleExportChat}
            title="Export chat"
            disabled={messages.length === 0}
          >
            <Download className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleCanvasCollapse}
            title={canvasCollapsed ? "Show canvas" : "Hide canvas"}
          >
            {canvasCollapsed ? (
              <PanelLeft className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </Button>
        </div>
      </header>

      {/* Messages */}
      <ScrollArea ref={scrollRef} className="flex-1">
        <div className="max-w-4xl mx-auto">
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center p-8">
              <div className="text-center space-y-2">
                <p className="text-lg font-medium">How can I help you today?</p>
                <p className="text-sm text-muted-foreground">
                  Ask anything. Attach documents. Get answers.
                </p>
              </div>
            </div>
          ) : (
            messages.map((message, idx) => (
              <MessageBubble
                key={message.id}
                message={message}
                isStreaming={
                  isStreaming &&
                  idx === messages.length - 1 &&
                  message.role === "assistant"
                }
              />
            ))
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <ChatInput onSend={handleSend} onStop={handleStop} isStreaming={isStreaming} />
    </div>
  );
}
