// frontend/src/components/chat/MessageContent.test.tsx
// Unit tests for MessageContent and MemoizedMarkdown components

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { MessageContent, MemoizedMarkdown } from "./MessageContent";
import type { Source } from "@/lib/api";

// Mock navigator.clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

// Mock the getRelevanceLabel function
vi.mock("@/lib/relevance", () => ({
  getRelevanceLabel: vi.fn().mockReturnValue({ text: "Relevant", color: "text-green-600" }),
}));

// =============================================================================
// TEST DATA
// =============================================================================

const createSource = (overrides: Partial<Source> = {}): Source => ({
  id: "src-1",
  filename: "test.md",
  snippet: "This is a <b>test</b> snippet",
  score: 0.3,
  score_type: "distance",
  ...overrides,
});

// =============================================================================
// TESTS
// =============================================================================

describe("MemoizedMarkdown", () => {
  describe("export", () => {
    it("is exported and can be imported", () => {
      expect(MemoizedMarkdown).toBeDefined();
      expect(typeof MemoizedMarkdown).toBe("object"); // React.memo returns an object
    });
  });

  describe("rendering", () => {
    it("renders markdown content correctly", () => {
      render(<MemoizedMarkdown content="**bold text**" />);
      expect(screen.getByText("bold text")).toBeInTheDocument();
    });

    it("renders GFM (GitHub Flavored Markdown) - tables", () => {
      const tableMarkdown = `
| Header |
|--------|
| Cell   |
`;
      render(<MemoizedMarkdown content={tableMarkdown} />);
      expect(screen.getByText("Header")).toBeInTheDocument();
      expect(screen.getByText("Cell")).toBeInTheDocument();
    });

    it("renders GFM - task lists", () => {
      const taskListMarkdown = `
- [x] Done
- [ ] Not done
`;
      render(<MemoizedMarkdown content={taskListMarkdown} />);
      expect(screen.getByText("Done")).toBeInTheDocument();
      expect(screen.getByText("Not done")).toBeInTheDocument();
    });
  });

  describe("streaming indicator", () => {
    it("shows streaming indicator when isStreaming=true", () => {
      render(<MemoizedMarkdown content="Loading..." isStreaming={true} />);
      const indicator = screen.getByRole("status", { name: /message streaming/i });
      expect(indicator).toBeInTheDocument();
    });

    it("does not show streaming indicator when isStreaming=false", () => {
      render(<MemoizedMarkdown content="Done" isStreaming={false} />);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("does not show streaming indicator when isStreaming is undefined", () => {
      render(<MemoizedMarkdown content="Done" />);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  describe("memoization", () => {
    it("re-renders when content changes", () => {
      const { rerender } = render(
        <MemoizedMarkdown content="First" isStreaming={false} />
      );
      expect(screen.getByText("First")).toBeInTheDocument();

      rerender(<MemoizedMarkdown content="Second" isStreaming={false} />);
      expect(screen.getByText("Second")).toBeInTheDocument();
      expect(screen.queryByText("First")).not.toBeInTheDocument();
    });

    it("re-renders when isStreaming changes", () => {
      const { rerender } = render(
        <MemoizedMarkdown content="Test" isStreaming={false} />
      );
      expect(screen.queryByRole("status")).not.toBeInTheDocument();

      rerender(<MemoizedMarkdown content="Test" isStreaming={true} />);
      expect(screen.getByRole("status")).toBeInTheDocument();

      rerender(<MemoizedMarkdown content="Test" isStreaming={false} />);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});

describe("MessageContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("markdown rendering", () => {
    it("renders markdown content correctly", () => {
      render(<MessageContent content="**bold** and *italic*" />);
      expect(screen.getByText("bold")).toBeInTheDocument();
      expect(screen.getByText("italic")).toBeInTheDocument();
    });

    it("renders code blocks", () => {
      render(<MessageContent content="```js\nconst x = 1;\n```" />);
      // The language tag and newlines are preserved in the output
      expect(screen.getByText(/const x = 1;/)).toBeInTheDocument();
    });

    it("renders links", () => {
      render(<MessageContent content="[Click here](https://example.com)" />);
      const link = screen.getByRole("link", { name: /click here/i });
      expect(link).toHaveAttribute("href", "https://example.com");
    });
  });

  describe("copy button", () => {
    it("renders copy button", () => {
      render(<MessageContent content="Test message" />);
      const copyButton = screen.getByRole("button", { name: /copy message/i });
      expect(copyButton).toBeInTheDocument();
    });

    it("copies content to clipboard when clicked", async () => {
      render(<MessageContent content="Copy me" />);
      const copyButton = screen.getByRole("button", { name: /copy message/i });

      fireEvent.click(copyButton);

      await waitFor(() => {
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith("Copy me");
      });
    });

    it("shows check icon after copying", async () => {
      render(<MessageContent content="Copy me" />);
      const copyButton = screen.getByRole("button", { name: /copy message/i });

      fireEvent.click(copyButton);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /copied to clipboard/i })).toBeInTheDocument();
      });
    });

    it("reverts to copy icon after 2 seconds", async () => {
      // Use real timers since clipboard.writeText is async and doesn't work with fake timers
      render(<MessageContent content="Copy me" />);
      const copyButton = screen.getByRole("button", { name: /copy message/i });

      fireEvent.click(copyButton);

      // After click, the button should show "Copied"
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /copied to clipboard/i })).toBeInTheDocument();
      });

      // Wait 2.5 seconds for the timeout to reset
      await new Promise((resolve) => setTimeout(resolve, 2500));

      expect(screen.getByRole("button", { name: /copy message/i })).toBeInTheDocument();
    });
  });

  describe("sources list", () => {
    it("renders sources when provided", () => {
      const sources = [
        createSource({ id: "src-1", filename: "doc1.md", snippet: "First snippet" }),
        createSource({ id: "src-2", filename: "doc2.md", snippet: "Second snippet" }),
      ];

      render(<MessageContent content="Response" sources={sources} />);

      expect(screen.getByText("Sources")).toBeInTheDocument();
      expect(screen.getByText("doc1.md")).toBeInTheDocument();
      expect(screen.getByText("doc2.md")).toBeInTheDocument();
    });

    it("does not render sources section when sources is empty array", () => {
      render(<MessageContent content="Response" sources={[]} />);
      expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    });

    it("does not render sources section when sources is undefined", () => {
      render(<MessageContent content="Response" />);
      expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    });

    it("renders source with relevance label", () => {
      const sources = [
        createSource({ id: "src-1", filename: "test.md", score: 0.1, score_type: "distance" }),
      ];

      render(<MessageContent content="Response" sources={sources} />);

      // The # and 1 are separate text nodes, so we use regex to match
      expect(screen.getByText(/#1/i)).toBeInTheDocument();
      // The text may be split across nodes due to the mock returning an object
      expect(screen.getByText(/Relevant/i)).toBeInTheDocument();
    });

    it("renders source snippet with escaped HTML", () => {
      const sources = [
        createSource({ id: "src-1", filename: "test.md", snippet: "<script>alert(1)</script>" }),
      ];

      render(<MessageContent content="Response" sources={sources} />);

      // The snippet should be escaped, not rendered as HTML
      const snippet = screen.getByText("<script>alert(1)</script>");
      expect(snippet).toBeInTheDocument();
      // Should not have an actual script element
      expect(document.querySelector("script")).not.toBeInTheDocument();
    });

    it("handles source without score gracefully", () => {
      const sources = [
        createSource({ id: "src-1", filename: "test.md", score: undefined }),
      ];

      render(<MessageContent content="Response" sources={sources} />);

      expect(screen.getByText("test.md")).toBeInTheDocument();
    });
  });

  describe("streaming indicator integration", () => {
    it("shows streaming indicator when isStreaming=true", () => {
      render(<MessageContent content="Streaming..." isStreaming={true} />);
      expect(screen.getByRole("status", { name: /message streaming/i })).toBeInTheDocument();
    });

    it("hides streaming indicator when isStreaming=false", () => {
      render(<MessageContent content="Done" isStreaming={false} />);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("hides streaming indicator when isStreaming is undefined", () => {
      render(<MessageContent content="Done" />);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
