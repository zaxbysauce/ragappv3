// frontend/src/components/chat/MessageContent.memoization.test.tsx
// Dedicated memoization proof test — mock is scoped to THIS FILE ONLY

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// Mock react-markdown BEFORE importing MemoizedMarkdown
// This mock is scoped to this file only — won't affect other test files
// We track render count to prove memoization works
let reactMarkdownRenderCount = 0;
vi.mock("react-markdown", () => ({
  default: ({ children }: { children: string }) => {
    reactMarkdownRenderCount++;
    return <div>{children}</div>;
  },
}));

// Mock remark-gfm and rehype-sanitize (required by the real component's imports)
vi.mock("remark-gfm", () => ({ default: () => {} }));
vi.mock("rehype-sanitize", () => ({ default: () => {} }));

// Mock other imports
vi.mock("lucide-react", () => ({ Copy: () => null, Check: () => null, FileText: () => null }));
vi.mock("@/components/ui/button", () => ({ Button: ({ children }: any) => <button>{children}</button> }));
vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: any) => <>{children}</>,
  TooltipContent: ({ children }: any) => <>{children}</>,
  TooltipProvider: ({ children }: any) => <>{children}</>,
  TooltipTrigger: ({ children, asChild }: any) => <>{children}</>,
}));
vi.mock("@/components/shared/CopyButton", () => ({ CopyButton: () => null }));
vi.mock("./SourceCitation", () => ({ SourceCitation: () => null }));
vi.mock("@/lib/api", () => ({}));
vi.mock("@/lib/relevance", () => ({ getRelevanceLabel: () => ({ text: "High" }) }));

// Import AFTER mocks
import { MemoizedMarkdown } from "./MessageContent";

describe("MemoizedMarkdown memoization", () => {
  beforeEach(() => {
    reactMarkdownRenderCount = 0;
  });

  it("skips re-render when props are unchanged", () => {
    const { rerender } = render(
      <MemoizedMarkdown content="test content" isStreaming={false} />
    );

    const afterInitialRender = reactMarkdownRenderCount;
    expect(afterInitialRender).toBe(1);

    // Re-render with IDENTICAL props
    rerender(<MemoizedMarkdown content="test content" isStreaming={false} />);
    rerender(<MemoizedMarkdown content="test content" isStreaming={false} />);
    rerender(<MemoizedMarkdown content="test content" isStreaming={false} />);

    // React.memo with default shallow compare on primitive props guarantees
    // the component did not re-execute its render function.
    // Since props didn't change, ReactMarkdown should NOT have been called again.
    expect(reactMarkdownRenderCount).toBe(afterInitialRender);

    // Verify the content is still rendered correctly
    expect(screen.getByText("test content")).toBeInTheDocument();
  });

  it("re-renders when content changes", () => {
    const { rerender } = render(
      <MemoizedMarkdown content="initial content" isStreaming={false} />
    );

    const afterInitialRender = reactMarkdownRenderCount;
    expect(afterInitialRender).toBe(1);

    // Re-render with DIFFERENT content
    rerender(<MemoizedMarkdown content="changed content" isStreaming={false} />);

    // Content changed, so ReactMarkdown SHOULD have been called again
    expect(reactMarkdownRenderCount).toBe(afterInitialRender + 1);

    // Verify the new content is rendered
    expect(screen.getByText("changed content")).toBeInTheDocument();
  });

  it("re-renders when isStreaming changes", () => {
    const { rerender } = render(
      <MemoizedMarkdown content="test content" isStreaming={false} />
    );

    // No streaming indicator initially
    expect(document.querySelector('[role="status"]')).not.toBeInTheDocument();

    // Re-render with isStreaming = true
    rerender(<MemoizedMarkdown content="test content" isStreaming={true} />);

    // Streaming indicator should now appear
    expect(document.querySelector('[role="status"]')).toBeInTheDocument();
  });
});
