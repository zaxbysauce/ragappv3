import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreVertical, Download, RotateCcw, Edit3, Plus } from "lucide-react";
import { VaultSelector } from "@/components/vault/VaultSelector";

interface ChatHeaderProps {
  chatTitle: string;
  isEditingTitle: boolean;
  messagesCount: number;
  onTitleChange: (title: string) => void;
  onStartEditTitle: () => void;
  onSaveTitle: () => void;
  onCancelEditTitle: () => void;
  onExportChat: () => void;
  onClearChat: () => void;
  onNewChat: () => void;
}

export function ChatHeader({
  chatTitle,
  isEditingTitle,
  messagesCount,
  onTitleChange,
  onStartEditTitle,
  onSaveTitle,
  onCancelEditTitle,
  onExportChat,
  onClearChat,
  onNewChat,
}: ChatHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        {isEditingTitle ? (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={chatTitle}
              onChange={(e) => onTitleChange(e.target.value)}
              placeholder="Chat title..."
              className="text-2xl font-bold bg-transparent border-b border-primary focus:outline-none focus:border-primary-foreground"
              onKeyDown={(e) => {
                if (e.key === "Enter") onSaveTitle();
                if (e.key === "Escape") onCancelEditTitle();
              }}
              autoFocus
            />
            <Button size="sm" onClick={onSaveTitle}>Save</Button>
          </div>
        ) : (
          <h1 className="text-3xl font-bold tracking-tight">Chat</h1>
        )}
        <p className="text-muted-foreground mt-1">Ask questions and get AI-powered answers</p>
      </div>
      <div className="flex items-center gap-2">
        <VaultSelector />

        {/* Chat Actions Dropdown */}
        {messagesCount > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" className="min-w-[44px] min-h-[44px]" aria-label="Chat actions">
                <MoreVertical className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onStartEditTitle}>
                <Edit3 className="w-4 h-4 mr-2" />
                Rename Chat
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onExportChat}>
                <Download className="w-4 h-4 mr-2" />
                Export to Text
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onClearChat} className="text-destructive focus:text-destructive">
                <RotateCcw className="w-4 h-4 mr-2" />
                Clear Chat
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        <Button variant="outline" size="sm" onClick={onNewChat}>
          <Plus className="w-4 h-4 mr-2" />
          New Chat
        </Button>
      </div>
    </div>
  );
}
