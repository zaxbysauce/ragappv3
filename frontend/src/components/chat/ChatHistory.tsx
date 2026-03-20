import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, MessageSquare } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import type { ChatSession } from "@/lib/api";

interface ChatHistoryProps {
  chatHistory: ChatSession[];
  isLoading: boolean;
  error: string | null;
  onLoadChat: (session: ChatSession) => Promise<void>;
  onSwitchToActive: () => void;
}

export function ChatHistory({
  chatHistory,
  isLoading,
  error,
  onLoadChat,
  onSwitchToActive,
}: ChatHistoryProps) {
  const handleLoadChat = async (session: ChatSession) => {
    await onLoadChat(session);
    onSwitchToActive();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Chat History</CardTitle>
        <CardDescription>View your past conversations</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-10 w-10 rounded-full" />
                <div className="space-y-2 flex-1">
                  <Skeleton className="h-4 w-[200px]" />
                  <Skeleton className="h-3 w-[150px]" />
                </div>
                <Skeleton className="h-3 w-[80px]" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <AlertCircle className="w-12 h-12 text-destructive mx-auto mb-4" />
            <p className="text-muted-foreground">Failed to load chat history.</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              {error}
            </p>
          </div>
        ) : chatHistory.length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title="No chat history yet"
            description="Start a conversation to see it here."
          />
        ) : (
          <div className="space-y-4">
            {chatHistory.map((session) => (
              <div
                key={session.id}
                className="flex items-center gap-4 p-3 rounded-lg hover:bg-muted/50 cursor-pointer transition-colors"
                onClick={() => handleLoadChat(session)}
              >
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <MessageSquare className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1">
                  <p className="font-medium">{session.title || "Untitled"}</p>
                  <p className="text-sm text-muted-foreground">Last active {new Date(session.updated_at).toLocaleString()}</p>
                </div>
                <span className="text-xs text-muted-foreground">{session.message_count ?? 0} messages</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
