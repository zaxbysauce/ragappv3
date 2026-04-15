import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Source } from "@/lib/api";
import { getRelevanceLabel } from "@/lib/relevance";

interface MessageContentProps {
  content: string;
  sources?: Source[];
  isStreaming?: boolean;
}

const escapeHtml = (unsafe: string): string => {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
};

export function MessageContent({ content, sources, isStreaming }: MessageContentProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    if (!navigator.clipboard) {
      return; // Silently fail - clipboard not available
    }
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group">
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{content}</ReactMarkdown>
        {isStreaming && (
          <span className="inline-block w-2 h-4 ml-1 bg-foreground animate-pulse" role="status" aria-live="polite" aria-label="Message streaming" />
        )}
      </div>

      {sources && sources.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-sm font-semibold mb-2 text-muted-foreground">Sources</p>
          <div className="space-y-2">
            {sources.map((source, index) => (
              <div
                key={source.id}
                className="text-xs p-2 rounded-md bg-muted/50 border border-border"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{source.filename}</span>
                  {source.score !== undefined && (
                    <span className="text-xs text-muted-foreground">
                      #{index + 1} · {getRelevanceLabel(source.score, source.score_type).text}
                    </span>
                  )}
                </div>
                {source.snippet && (
                  <p
                    className="mt-1 text-muted-foreground line-clamp-2"
                    dangerouslySetInnerHTML={{ __html: escapeHtml(source.snippet) }}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <Button
        variant="ghost"
        size="icon"
        className="absolute -right-10 top-0 opacity-40 hover:opacity-100 focus-visible:opacity-100 transition-opacity"
        onClick={handleCopy}
        aria-label={copied ? "Copied to clipboard" : "Copy message to clipboard"}
      >
        {copied ? (
          <Check className="h-4 w-4 text-green-500" />
        ) : (
          <Copy className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
}
