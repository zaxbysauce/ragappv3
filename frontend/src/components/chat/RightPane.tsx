import { useState, useMemo, useCallback, useEffect } from "react";
import { FileText, Table, Code, ExternalLink } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useChatStore, type Message } from "@/stores/useChatStore";
import { useChatShellStore } from "@/stores/useChatShellStore";
import type { Source } from "@/lib/api";
import { getRelevanceLabel, type ScoreType } from "@/lib/relevance";

interface StructuredOutput {
  id: string;
  type: "code" | "table";
  title: string;
  content: string;
  size: number;
}

/**
 * Escape regex special characters in a string
 */
function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Highlight query terms in text by wrapping matches in <mark> elements
 */
function highlightQueryTerms(text: string, query: string): React.ReactNode[] {
  if (!query.trim()) {
    return [text];
  }

  const terms = query
    .split(/\s+/)
    .filter((term) => term.length > 0)
    .map((term) => escapeRegex(term));

  if (terms.length === 0) {
    return [text];
  }

  const pattern = new RegExp(`(${terms.join("|")})`, "gi");
  const parts = text.split(pattern);

  return parts.map((part, index) => {
    if (terms.some((term) => part.toLowerCase() === term.toLowerCase())) {
      return (
        <mark
          key={index}
          className="bg-amber-200 dark:bg-amber-800 rounded px-0.5"
        >
          {part}
        </mark>
      );
    }
    return part;
  });
}

/**
 * Extract structured outputs (code blocks and tables) from assistant messages
 */
function extractStructuredOutputs(messages: Message[]): StructuredOutput[] {
  const outputs: StructuredOutput[] = [];

  for (const message of messages) {
    if (message.role !== "assistant") continue;

    const content = message.content;
    if (!content) continue;

    // Extract code blocks (```...```)
    const codeBlockRegex = /```(?:(\w+)?\n)?([\s\S]*?)```/g;
    let codeMatch;
    while ((codeMatch = codeBlockRegex.exec(content)) !== null) {
      const language = codeMatch[1] || "";
      const codeContent = codeMatch[2].trim();
      const lines = codeContent.split("\n");
      const firstLine = lines[0] || "Code Block";
      const title = language
        ? `${language.charAt(0).toUpperCase() + language.slice(1)} Block`
        : firstLine.length > 30
          ? firstLine.slice(0, 30) + "..."
          : firstLine;

      // Generate a simple hash-based ID
      const id = `code-${codeContent.slice(0, 50).replace(/\s/g, "").slice(0, 20)}`;

      outputs.push({
        id,
        type: "code",
        title: title || "Code Block",
        content: codeContent,
        size: lines.length,
      });
    }

    // Extract markdown tables (lines starting with |)
    const lines = content.split("\n");
    let inTable = false;
    let tableStart = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      const isTableLine = line.startsWith("|");

      if (isTableLine && !inTable) {
        inTable = true;
        tableStart = i;
      } else if (!isTableLine && inTable) {
        // Table ended
        const tableLines = lines.slice(tableStart, i);
        // Filter out separator lines (like |---|---|)
        const contentLines = tableLines.filter(
          (l) => !/^\|[-:|\s]+\|$/.test(l.trim())
        );
        const tableContent = tableLines.join("\n");
        const firstDataLine = contentLines[0] || "";
        const cells = firstDataLine
          .split("|")
          .filter((c) => c.trim())
          .map((c) => c.trim());
        const title =
          cells.slice(0, 2).join(" | ").slice(0, 40) || "Table";

        // Generate a simple hash-based ID
        const id = `table-${tableContent.slice(0, 50).replace(/\s/g, "").slice(0, 20)}`;

        outputs.push({
          id,
          type: "table",
          title: title.length > 40 ? title.slice(0, 40) + "..." : title,
          content: tableContent,
          size: contentLines.length,
        });

        inTable = false;
      }
    }

    // Handle table that goes to end of content
    if (inTable) {
      const tableLines = lines.slice(tableStart);
      const contentLines = tableLines.filter(
        (l) => !/^\|[-:|\s]+\|$/.test(l.trim())
      );
      const tableContent = tableLines.join("\n");
      const firstDataLine = contentLines[0] || "";
      const cells = firstDataLine
        .split("|")
        .filter((c) => c.trim())
        .map((c) => c.trim());
      const title =
        cells.slice(0, 2).join(" | ").slice(0, 40) || "Table";

      const id = `table-${tableContent.slice(0, 50).replace(/\s/g, "").slice(0, 20)}`;

      outputs.push({
        id,
        type: "table",
        title: title.length > 40 ? title.slice(0, 40) + "..." : title,
        content: tableContent,
        size: contentLines.length,
      });
    }
  }

  return outputs;
}

interface SourceListItemProps {
  source: Source;
  index: number;
  isSelected: boolean;
  scoreType?: ScoreType;
  onClick: () => void;
}

function SourceListItem({
  source,
  index,
  isSelected,
  scoreType,
  onClick,
}: SourceListItemProps) {
  const relevance =
    source.score !== undefined
      ? getRelevanceLabel(source.score, scoreType)
      : null;

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left p-3 rounded-lg border transition-all",
        "hover:bg-accent/50 hover:border-accent",
        isSelected
          ? "bg-accent border-primary ring-1 ring-primary"
          : "bg-card border-border"
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
            <span className="text-sm font-medium truncate">
              {source.filename}
            </span>
          </div>
          {source.snippet && (
            <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
              {source.snippet.slice(0, 60)}
              {source.snippet.length > 60 ? "..." : ""}
            </div>
          )}
          {relevance && (
            <div className={cn("text-xs mt-1", relevance.color)}>
              {relevance.text}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

interface SourcePreviewProps {
  source: Source;
  query: string;
  onJumpToAnswer: () => void;
}

function SourcePreview({ source, query, onJumpToAnswer }: SourcePreviewProps) {
  const content = source.snippet || "";
  const highlightedContent = useMemo(
    () => highlightQueryTerms(content, query),
    [content, query]
  );

  return (
    <div className="flex flex-col h-full min-h-0 gap-4">
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-primary" />
          <h3 className="font-semibold">{source.filename}</h3>
        </div>
        <Button variant="ghost" size="sm" onClick={onJumpToAnswer}>
          <ExternalLink className="h-3.5 w-3.5 mr-1" />
          Jump to answer
        </Button>
      </div>

      {source.snippet && (
        <div className="text-xs text-muted-foreground italic truncate flex-shrink-0">
          {source.snippet.slice(0, 100)}
          {source.snippet.length > 100 ? "..." : ""}
        </div>
      )}

      {source.score !== undefined && source.score_type && (
        <div className="flex items-center gap-2 text-sm flex-shrink-0">
          <span className="text-muted-foreground">Relevance:</span>
          <span className={getRelevanceLabel(source.score, source.score_type).color}>
            {getRelevanceLabel(source.score, source.score_type).text}
          </span>
        </div>
      )}

      <ScrollArea className="flex-1 min-h-0 rounded-md border p-4">
        <div className="text-sm leading-relaxed whitespace-pre-wrap">
          {highlightedContent}
        </div>
      </ScrollArea>
    </div>
  );
}

interface StructuredOutputItemProps {
  output: StructuredOutput;
}

function StructuredOutputItem({ output }: StructuredOutputItemProps) {
  const Icon = output.type === "code" ? Code : Table;
  const label = output.type === "code" ? "Code" : "Table";

  return (
    <div className="p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-4 w-4 text-primary" />
        <span className="text-xs font-medium text-muted-foreground uppercase">
          {label}
        </span>
      </div>
      <div className="font-medium text-sm truncate">{output.title}</div>
      <div className="text-xs text-muted-foreground mt-1">
        {output.size} {output.type === "code" ? "lines" : "rows"}
      </div>
    </div>
  );
}

export function RightPane() {
  const { messages } = useChatStore();
  const { selectedEvidenceSource, setSelectedEvidenceSource, activeRightTab, setActiveRightTab } = useChatShellStore();
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [activeTab, setActiveTab] = useState<string>("sources");

  // Sync with store - when selectedEvidenceSource changes, update local state and switch to evidence tab
  useEffect(() => {
    if (selectedEvidenceSource) {
      setSelectedSource(selectedEvidenceSource);
    }
  }, [selectedEvidenceSource]);

  // Sync active tab with store
  useEffect(() => {
    if (activeRightTab === "evidence") {
      setActiveTab("sources");
    } else if (activeRightTab === "preview") {
      setActiveTab("preview");
    }
  }, [activeRightTab]);

  // Get sources from the last assistant message
  const sources = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].sources) {
        return (messages[i].sources || []).filter((s): s is Source => s != null);
      }
    }
    return [];
  }, [messages]);

  // Get query from the last user message
  const query = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        return messages[i].content;
      }
    }
    return "";
  }, [messages]);

  // Extract structured outputs from assistant messages
  const structuredOutputs = useMemo(
    () => extractStructuredOutputs(messages),
    [messages]
  );

  const handleSourceClick = useCallback((source: Source) => {
    setSelectedSource(source);
    setSelectedEvidenceSource(source);
    setActiveTab("preview");
    setActiveRightTab("preview");
  }, [setSelectedEvidenceSource, setActiveRightTab]);

  const handleJumpToAnswer = useCallback(() => {
    // Dispatch custom event for the transcript pane to handle
    if (selectedSource) {
      window.dispatchEvent(
        new CustomEvent("evidence:jump-to-answer", {
          detail: { sourceId: selectedSource.id },
        })
      );
    }
  }, [selectedSource]);

  const hasSources = sources.length > 0;
  const hasStructuredOutputs = structuredOutputs.length > 0;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Details
        </h2>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="flex-1 flex flex-col min-h-0"
      >
        <TabsList className="grid w-full grid-cols-3 flex-shrink-0">
          <TabsTrigger value="sources">
            Sources
            {hasSources && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({sources.length})
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="preview" disabled={!selectedSource}>
            Preview
          </TabsTrigger>
          <TabsTrigger value="extracted" disabled={!hasStructuredOutputs}>
            Extracted
            {hasStructuredOutputs && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({structuredOutputs.length})
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sources" className="flex-1 min-h-0 mt-4">
          <ScrollArea className="h-full">
            {!hasSources ? (
              <div className="text-sm text-muted-foreground italic p-4 text-center">
                No sources available. Send a message to see retrieved sources.
              </div>
            ) : (
              <div className="space-y-2 pr-4">
                {sources.map((source, index) => (
                  <SourceListItem
                    key={source.id}
                    source={source}
                    index={index}
                    isSelected={selectedSource?.id === source.id || selectedEvidenceSource?.id === source.id}
                    scoreType={source.score_type}
                    onClick={() => handleSourceClick(source)}
                  />
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        <TabsContent value="preview" className="flex-1 min-h-0 mt-4">
          {!selectedSource ? (
            <div className="text-sm text-muted-foreground italic p-4 text-center">
              Select a source from the Sources tab to preview it here.
            </div>
          ) : (
            <SourcePreview
              source={selectedSource}
              query={query}
              onJumpToAnswer={handleJumpToAnswer}
            />
          )}
        </TabsContent>

        <TabsContent value="extracted" className="flex-1 min-h-0 mt-4">
          <ScrollArea className="h-full">
            {!hasStructuredOutputs ? (
              <div className="text-sm text-muted-foreground italic p-4 text-center">
                No structured outputs found in the conversation.
              </div>
            ) : (
              <div className="space-y-2 pr-4">
                {structuredOutputs.map((output) => (
                  <StructuredOutputItem key={output.id} output={output} />
                ))}
              </div>
            )}
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default RightPane;
