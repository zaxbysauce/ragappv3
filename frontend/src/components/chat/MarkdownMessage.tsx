import { memo, useMemo, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { CopyButton } from "@/components/shared/CopyButton";
import { SourceCitation } from "./SourceCitation";
import type { Source, UsedMemory, WikiReference } from "@/lib/api";

// =============================================================================
// Syntax highlighter — lazily loaded so first chat render is not penalized
// =============================================================================

type HighlightFn = (code: string, lang: string) => Promise<string>;

let _highlightFn: HighlightFn | null = null;
let _highlightPromise: Promise<HighlightFn> | null = null;

function loadHighlighter(): Promise<HighlightFn> {
  if (_highlightFn) return Promise.resolve(_highlightFn);
  if (_highlightPromise) return _highlightPromise;

  _highlightPromise = (async () => {
    try {
      const { createHighlighter } = await import("shiki");
      const hl = await createHighlighter({
        themes: ["github-light", "github-dark"],
        langs: [
          "javascript", "typescript", "tsx", "jsx",
          "python", "bash", "sh", "json", "yaml", "toml",
          "css", "html", "xml", "markdown", "sql",
          "rust", "go", "java", "c", "cpp", "csharp",
        ],
      });
      const fn: HighlightFn = (code, lang) => {
        const isDark = document.documentElement.classList.contains("dark");
        try {
          return Promise.resolve(
            hl.codeToHtml(code, {
              lang: lang || "text",
              theme: isDark ? "github-dark" : "github-light",
            })
          );
        } catch {
          // Unknown language — fallback to plain text
          return Promise.resolve(
            hl.codeToHtml(code, { lang: "text", theme: isDark ? "github-dark" : "github-light" })
          );
        }
      };
      _highlightFn = fn;
      return fn;
    } catch {
      // Shiki unavailable — return no-op so code still renders as plain text
      const fn: HighlightFn = (code) => Promise.resolve(`<pre><code>${code}</code></pre>`);
      _highlightFn = fn;
      return fn;
    }
  })();

  return _highlightPromise;
}

// =============================================================================
// CodeBlock with syntax highlighting
// =============================================================================

interface CodeBlockProps {
  language: string;
  code: string;
}

const CodeBlock = memo(function CodeBlock({ language, code }: CodeBlockProps) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadHighlighter().then((highlight) => {
      highlight(code, language).then((result) => {
        if (!cancelled) setHtml(result);
      });
    });
    return () => { cancelled = true; };
  }, [code, language]);

  return (
    <div className="relative my-3 rounded-lg overflow-hidden border border-border group/code">
      {language && (
        <div className="flex items-center justify-between px-4 py-1.5 bg-muted border-b border-border">
          <span className="text-[11px] text-muted-foreground font-mono">{language}</span>
          <CopyButton text={code} label="Copy code" className="h-6 w-6 opacity-60 hover:opacity-100" />
        </div>
      )}
      {!language && (
        <CopyButton
          text={code}
          label="Copy code"
          className="absolute top-2 right-2 h-6 w-6 opacity-0 group-hover/code:opacity-100 focus:opacity-100 transition-opacity z-10"
        />
      )}
      {html ? (
        <div
          className="shiki-wrapper overflow-x-auto text-sm [&>pre]:p-4 [&>pre]:m-0 [&>pre]:rounded-none [&>pre]:bg-transparent"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="overflow-x-auto p-4 text-sm font-mono bg-muted/40">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
});

// =============================================================================
// Citation-aware markdown renderer
// =============================================================================

interface ParsedSegment {
  type: "text" | "citation" | "memory_citation" | "wiki_citation";
  content?: string;
  sourceName?: string;
  memoryLabel?: string;
  wikiLabel?: string;
}

/**
 * Parse citation markers from assistant text:
 * - ``[S1]``, ``[S2]`` — document citations
 * - ``[M1]``, ``[M2]`` — memory citations (durable user context)
 * - ``[W1]``, ``[W2]`` — wiki knowledge citations
 * - ``[Source: filename]`` — legacy filename citation
 *
 * Returns text/citation segments so a single ReactMarkdown pass runs per
 * text segment while citations are rendered as interactive chips.
 */
export function parseCitationSegments(
  content: string,
  sources: Source[] | undefined,
  memories?: UsedMemory[],
  wikiRefs?: WikiReference[]
): { segments: ParsedSegment[]; citedSources: Source[]; citedMemories: UsedMemory[]; citedWikis: WikiReference[] } {
  // Capture groups:
  //  1. document number (e.g. "2" from "[S2]")
  //  2. memory number   (e.g. "1" from "[M1]")
  //  3. wiki number     (e.g. "3" from "[W3]")
  //  4. legacy filename (e.g. "report.pdf" from "[Source: report.pdf]")
  const regex = /\[S(\d+)\]|\[M(\d+)\]|\[W(\d+)\]|\[Source:\s*([^\]]+)\]/g;
  const segments: ParsedSegment[] = [];
  const citedSources: Source[] = [];
  const citedMemories: UsedMemory[] = [];
  const citedWikis: WikiReference[] = [];
  const seenSourceIds = new Set<string>();
  const seenMemoryIds = new Set<string>();
  const seenWikiLabels = new Set<string>();
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", content: content.slice(lastIndex, match.index) });
    }

    if (match[1]) {
      // Document citation [S#]
      const label = `S${match[1]}`;
      let source = sources?.find((s) => s.source_label === label);
      if (!source) {
        const idx = parseInt(match[1], 10) - 1;
        if (sources && idx >= 0 && idx < sources.length) source = sources[idx];
      }
      segments.push({ type: "citation", sourceName: label });
      if (source && !seenSourceIds.has(source.id)) {
        citedSources.push(source);
        seenSourceIds.add(source.id);
      }
    } else if (match[2]) {
      // Memory citation [M#]
      const label = `M${match[2]}`;
      let memory = memories?.find((m) => m.memory_label === label);
      if (!memory) {
        const idx = parseInt(match[2], 10) - 1;
        if (memories && idx >= 0 && idx < memories.length) memory = memories[idx];
      }
      segments.push({ type: "memory_citation", memoryLabel: label });
      if (memory && !seenMemoryIds.has(memory.id)) {
        citedMemories.push(memory);
        seenMemoryIds.add(memory.id);
      }
    } else if (match[3]) {
      // Wiki citation [W#]
      const label = `W${match[3]}`;
      let wiki = wikiRefs?.find((w) => w.wiki_label === label);
      if (!wiki) {
        const idx = parseInt(match[3], 10) - 1;
        if (wikiRefs && idx >= 0 && idx < wikiRefs.length) wiki = wikiRefs[idx];
      }
      segments.push({ type: "wiki_citation", wikiLabel: label });
      if (wiki && !seenWikiLabels.has(label)) {
        citedWikis.push(wiki);
        seenWikiLabels.add(label);
      }
    } else if (match[4]) {
      // Legacy [Source: filename]
      const sourceName = match[4].trim();
      const source = sources?.find((s) => s.filename === sourceName);
      segments.push({ type: "citation", sourceName });
      if (source && !seenSourceIds.has(source.id)) {
        citedSources.push(source);
        seenSourceIds.add(source.id);
      }
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < content.length) {
    segments.push({ type: "text", content: content.slice(lastIndex) });
  }

  return { segments, citedSources, citedMemories, citedWikis };
}

// Stable plugin arrays — prevent re-creating on every render
const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeSanitize];

interface MarkdownMessageProps {
  content: string;
  sources?: Source[];
  memories?: UsedMemory[];
  wikiRefs?: WikiReference[];
  isStreaming?: boolean;
  onCitationClick?: (source: Source) => void;
  onMemoryCitationClick?: (memory: UsedMemory) => void;
  onWikiCitationClick?: (wiki: WikiReference) => void;
  citedSources?: Source[];
}

/**
 * Unified markdown + citation renderer used by both assistant and user messages.
 *
 * - Renders one ReactMarkdown instance per text segment (between citations).
 * - Lazily loads Shiki for syntax-highlighted code blocks.
 * - Inline citation chips are interactive and call onCitationClick.
 * - Streaming caret blinks while isStreaming is true.
 */
export const MarkdownMessage = memo(function MarkdownMessage({
  content,
  sources,
  memories,
  wikiRefs,
  isStreaming,
  onCitationClick,
  onMemoryCitationClick,
  onWikiCitationClick,
  citedSources: externalCitedSources,
}: MarkdownMessageProps) {
  const { segments, citedSources: internalCitedSources } = useMemo(
    () => parseCitationSegments(content, sources, memories, wikiRefs),
    [content, sources, memories, wikiRefs]
  );

  const citedSources = externalCitedSources ?? internalCitedSources;

  const nodes = useMemo(() => {
    return segments.map((segment, i) => {
      if (segment.type === "wiki_citation") {
        const label = segment.wikiLabel ?? "";
        const wiki =
          wikiRefs?.find((w) => w.wiki_label === label) ??
          (() => {
            const m = label.match(/^W(\d+)$/);
            if (m && wikiRefs) {
              const idx = parseInt(m[1], 10) - 1;
              return idx >= 0 && idx < wikiRefs.length ? wikiRefs[idx] : undefined;
            }
            return undefined;
          })();
        const titleText = wiki
          ? `Wiki ${label}: ${wiki.title}${wiki.claim_text ? ` — ${wiki.claim_text.slice(0, 100)}` : ""}`
          : `Wiki ${label}`;
        return (
          <button
            key={`wiki-${i}`}
            type="button"
            className="inline-flex items-center align-baseline px-1.5 py-0.5 mx-0.5 rounded-md border border-indigo-500/40 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 text-[10px] font-semibold tracking-wide hover:bg-indigo-500/20 hover:border-indigo-500/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => wiki && onWikiCitationClick?.(wiki)}
            disabled={!wiki}
            title={titleText}
            aria-label={titleText}
            data-citation-type="wiki"
            data-citation-label={label}
          >
            {label}
          </button>
        );
      }
      if (segment.type === "memory_citation") {
        const label = segment.memoryLabel ?? "";
        const memory =
          memories?.find((m) => m.memory_label === label) ||
          (() => {
            const m = label.match(/^M(\d+)$/);
            if (m && memories) {
              const idx = parseInt(m[1], 10) - 1;
              return idx >= 0 && idx < memories.length ? memories[idx] : undefined;
            }
            return undefined;
          })();
        const titleText = memory?.content
          ? `Memory ${label}: ${memory.content.slice(0, 200)}${memory.content.length > 200 ? "…" : ""}`
          : `Memory ${label}`;
        return (
          <button
            key={`mem-${i}`}
            type="button"
            className="inline-flex items-center align-baseline px-1.5 py-0.5 mx-0.5 rounded-md border border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300 text-[10px] font-semibold tracking-wide hover:bg-amber-500/20 hover:border-amber-500/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => memory && onMemoryCitationClick?.(memory)}
            disabled={!memory}
            title={titleText}
            aria-label={titleText}
            data-citation-type="memory"
            data-citation-label={label}
          >
            {label}
          </button>
        );
      }
      if (segment.type === "citation") {
        const name = segment.sourceName ?? "";
        // Resolve the source
        const source =
          sources?.find((s) => s.source_label === name) ||
          sources?.find((s) => s.filename === name) ||
          (() => {
            const m = name.match(/^S(\d+)$/);
            if (m && sources) {
              const idx = parseInt(m[1], 10) - 1;
              return idx >= 0 && idx < sources.length ? sources[idx] : undefined;
            }
            return undefined;
          })();

        if (source) {
          const dispIdx = citedSources.findIndex((s) => s.id === source.id);
          return (
            <SourceCitation
              key={`cit-${i}`}
              source={source}
              index={dispIdx >= 0 ? dispIdx : i}
              onClick={() => onCitationClick?.(source)}
              variant="inline"
            />
          );
        }
        return <span key={`cit-${i}`}>[{name}]</span>;
      }

      return (
        <ReactMarkdown
          key={`text-${i}`}
          remarkPlugins={REMARK_PLUGINS}
          rehypePlugins={REHYPE_PLUGINS}
          components={{
            p: ({ children }) => <>{children}</>,
            pre: ({ children }) => <>{children}</>,
            code: ({ className, children }) => {
              const isBlock = Boolean(className?.startsWith("language-"));
              if (!isBlock) {
                return (
                  <code className="bg-muted px-1 py-0.5 rounded text-[0.85em] font-mono">
                    {children}
                  </code>
                );
              }
              const lang = className?.replace("language-", "") ?? "";
              const codeText = String(children).replace(/\n$/, "");
              return <CodeBlock language={lang} code={codeText} />;
            },
          }}
        >
          {segment.content ?? ""}
        </ReactMarkdown>
      );
    });
  }, [segments, citedSources, sources, memories, wikiRefs, onCitationClick, onMemoryCitationClick, onWikiCitationClick]);

  return (
    <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-headings:font-sans prose-headings:mt-4 prose-headings:mb-1 prose-strong:font-semibold prose-p:leading-relaxed prose-p:mb-3 prose-p:mt-0 prose-li:my-0.5 prose-ul:my-2 prose-ol:my-2 prose-blockquote:border-l-2 prose-blockquote:border-primary/40 prose-blockquote:pl-3 prose-blockquote:italic prose-code:font-mono">
      {nodes}
      {isStreaming && (
        <span
          className="streaming-caret"
          role="status"
          aria-label="Message streaming"
        />
      )}
    </div>
  );
});
