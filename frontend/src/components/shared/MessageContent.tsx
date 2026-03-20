import { MarkdownContent } from "./MarkdownContent";
import type { Message } from "@/stores/useChatStore";
import type { Source } from "@/lib/api";
import React from "react";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface SourcesListProps {
  sources: Source[];
}

const SourcesList = React.memo(function SourcesList({ sources }: SourcesListProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 border-t pt-3 border-gray-200 dark:border-gray-700">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors w-full text-left"
        aria-expanded={isExpanded}
        aria-label={`${isExpanded ? 'Hide' : 'Show'} sources (${sources.length})`}
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4" />
        ) : (
          <ChevronRight className="w-4 h-4" />
        )}
        <span className="font-medium">Sources ({sources.length})</span>
      </button>

      {isExpanded && (
        <div className="mt-2 space-y-2">
          {sources.map((source) => (
            <div
              key={source.id}
              className="rounded-md border border-gray-200 dark:border-gray-700 p-3 bg-gray-50 dark:bg-gray-800/50"
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">
                  {source.filename}
                </span>
                <Badge variant="secondary" className="text-xs">
                  {source.score ? `${Math.round(source.score * 100)}%` : 'N/A'}
                </Badge>
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">
                {source.snippet?.substring(0, 100)}
                {source.snippet && source.snippet.length > 100 ? '...' : ''}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export const MessageContent = React.memo(function MessageContent({ message }: { message: Message }) {
  const assistantContent = message.role === "assistant" ? (
    <>
      <MarkdownContent content={message.content} />
      {message.sources && <SourcesList sources={message.sources} />}
    </>
  ) : (
    <span className="whitespace-pre-wrap">{message.content}</span>
  );

  return assistantContent;
});
