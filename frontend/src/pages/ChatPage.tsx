import { useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useChatStore, type Message } from "@/stores/useChatStore";
import { useVaultStore } from "@/stores/useVaultStore";
import { useChatHistory } from "@/hooks/useChatHistory";
import { useSendMessage, MAX_INPUT_LENGTH } from "@/hooks/useSendMessage";
import { KeyboardShortcutsDialog, useKeyboardShortcuts } from "@/components/shared/KeyboardShortcuts";
import { MessageContent } from "@/components/shared/MessageContent";
import { MessageActions } from "@/components/shared/MessageActions";
import { updateChatSession } from "@/lib/api";
import { toast } from "sonner";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { ChatHistory } from "@/components/chat/ChatHistory";
import { SourcesPanel } from "@/components/chat/SourcesPanel";
import { ClearChatDialog } from "@/components/chat/ClearChatDialog";
import { ErrorBoundary } from "../components/ErrorBoundary";

export default function ChatPage() {
  const {
    messages,
    input,
    isStreaming,
    inputError,
    expandedSources,
    toggleSource,
  } = useChatStore();
  const { activeVaultId } = useVaultStore();

  const [activeTab, setActiveTab] = useState("active");
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [chatTitle, setChatTitle] = useState("");
  const [isEditingTitle, setIsEditingTitle] = useState(false);

  // Keyboard shortcuts
  const { open: shortcutsOpen, setOpen: setShortcutsOpen } = useKeyboardShortcuts();

  // Chat history logic
  const { chatHistory, isChatLoading, chatHistoryError, handleLoadChat, refreshHistory } =
    useChatHistory(activeVaultId);

  // Send message logic
  const { handleSend, handleStop, handleKeyDown, handleInputChange } = useSendMessage(
    activeVaultId,
    refreshHistory
  );

  const { latestAssistantMessage } = useMemo(() => {
    const latest = messages.filter((m) => m.role === "assistant").pop();
    return {
      latestAssistantMessage: latest,
    };
  }, [messages]);

  const handleClearChat = () => {
    useChatStore.getState().clearMessages();
    setShowClearDialog(false);
  };

  const handleExportChat = () => {
    const chatText = messages.map(m => {
      const role = m.role === "user" ? "User" : "Assistant";
      return `${role}: ${m.content}`;
    }).join("\n\n");

    const blob = new Blob([chatText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleSaveTitle = async () => {
    const { activeChatId } = useChatStore.getState();
    if (activeChatId && chatTitle.trim()) {
      try {
        await updateChatSession(Number(activeChatId), chatTitle.trim());
        toast.success("Chat title saved");
      } catch (error) {
        toast.error("Failed to save chat title");
        console.error("Error saving chat title:", error);
      }
    }
    setIsEditingTitle(false);
  };

  const handleToggleSource = (sourceId: string) => {
    toggleSource(sourceId);
  };

  return (
    <ErrorBoundary>
      <div className="space-y-6 animate-in fade-in duration-300">
      <ChatHeader
        chatTitle={chatTitle}
        isEditingTitle={isEditingTitle}
        messagesCount={messages.length}
        onTitleChange={setChatTitle}
        onStartEditTitle={() => setIsEditingTitle(true)}
        onSaveTitle={handleSaveTitle}
        onCancelEditTitle={() => setIsEditingTitle(false)}
        onExportChat={handleExportChat}
        onClearChat={() => setShowClearDialog(true)}
        onNewChat={() => useChatStore.getState().newChat()}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full max-w-md grid-cols-2">
              <TabsTrigger value="active">Active Chats</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>

            <TabsContent value="active" className="space-y-4">
              <ActiveChatTab
                messages={messages}
                input={input}
                isStreaming={isStreaming}
                inputError={inputError}
                onInputChange={handleInputChange}
                onKeyDown={handleKeyDown}
                onSend={handleSend}
                onStop={handleStop}
              />
            </TabsContent>

            <TabsContent value="history">
              <ChatHistory
                chatHistory={chatHistory}
                isLoading={isChatLoading}
                error={chatHistoryError}
                onLoadChat={handleLoadChat}
                onSwitchToActive={() => setActiveTab("active")}
              />
            </TabsContent>
          </Tabs>
        </div>

        <div className="lg:col-span-1">
          <SourcesPanel
            sources={latestAssistantMessage?.sources}
            expandedSources={expandedSources}
            onToggleSource={handleToggleSource}
          />
        </div>
      </div>

      <ClearChatDialog
        open={showClearDialog}
        onOpenChange={setShowClearDialog}
        onConfirm={handleClearChat}
      />

      <KeyboardShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
      </div>
    </ErrorBoundary>
  );
}

// Active Chat Tab Component
interface ActiveChatTabProps {
  messages: Message[];
  input: string;
  isStreaming: boolean;
  inputError: string | null;
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSend: () => void;
  onStop: () => void;
}

function ActiveChatTab({
  messages,
  input,
  isStreaming,
  inputError,
  onInputChange,
  onKeyDown,
  onSend,
  onStop,
}: ActiveChatTabProps) {
  return (
    <>
      {messages.length > 0 && (
        <Card className="min-h-[300px] max-h-[500px] overflow-y-auto">
          <CardContent
            className="space-y-4 pt-6"
            role="log"
            aria-live="polite"
            aria-atomic="false"
            aria-label="Chat messages"
          >
            {messages.map((message, index) => (
              <ChatMessageItem
                key={message.id}
                message={message}
                isStreaming={isStreaming && index === messages.length - 1 && message.role === "assistant"}
              />
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {messages.length === 0 ? "Start a New Conversation" : "Continue Chatting"}
          </CardTitle>
          <CardDescription>
            Type your question below to start chatting with the AI
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Textarea
              placeholder="Ask anything about your documents..."
              className={`min-h-[120px] resize-none ${inputError ? "border-destructive focus-visible:ring-destructive" : ""}`}
              value={input}
              onChange={onInputChange}
              onKeyDown={onKeyDown}
              disabled={isStreaming}
              maxLength={MAX_INPUT_LENGTH}
              aria-label="Message input"
              aria-describedby={inputError ? "input-error" : undefined}
            />
            <div className="flex justify-between items-center">
              {inputError ? (
                <span id="input-error" className="text-xs text-destructive" role="alert">{inputError}</span>
              ) : (
                <span className="text-xs text-muted-foreground"></span>
              )}
              <span className={`text-xs ${input.length > MAX_INPUT_LENGTH ? "text-destructive" : "text-muted-foreground"}`}>
                {input.length}/{MAX_INPUT_LENGTH}
              </span>
            </div>
          </div>
          <div className="flex justify-end">
            {isStreaming ? (
              <Button variant="destructive" onClick={onStop}>
                Stop
              </Button>
            ) : (
              <Button onClick={onSend} disabled={!input.trim()}>
                Send Message
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </>
  );
}

// Chat Message Item Component
interface ChatMessageItemProps {
  message: Message;
  isStreaming?: boolean;
}

function ChatMessageItem({ message, isStreaming }: ChatMessageItemProps) {
  return (
    <div
      className={`flex ${
        message.role === "user" ? "justify-end" : "justify-start"
      }`}
    >
      <div
        className={`group max-w-[80%] rounded-lg p-4 relative ${
          message.role === "user"
            ? "bg-primary text-primary-foreground"
            : "bg-muted"
        }`}
      >
        <div className="text-sm">
          <MessageContent message={message} />
          {isStreaming && (
            <span className="inline-block w-2 h-4 ml-1 bg-current animate-pulse"></span>
          )}
        </div>
        {message.error && (
          <div className="mt-2 text-xs text-destructive">
            Error: {message.error}
          </div>
        )}
        {message.stopped && (
          <div className="mt-2 text-xs text-muted-foreground italic">
            [stopped]
          </div>
        )}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border/50">
            <p className="text-xs font-medium mb-1">Sources:</p>
            <div className="flex flex-wrap gap-1">
              {message.sources.map((source) => (
                <Badge key={source.id} variant="secondary" className="text-xs">
                  {source.filename}
                </Badge>
              ))}
            </div>
          </div>
        )}
        <div className={`absolute -bottom-3 ${message.role === "user" ? "left-0" : "right-0"}`}>
          <MessageActions content={message.content} />
        </div>
      </div>
    </div>
  );
}
