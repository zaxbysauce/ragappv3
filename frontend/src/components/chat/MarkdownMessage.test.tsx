import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  MarkdownMessage,
  MarkdownMessageTestInternals,
  parseCitationSegments,
} from "./MarkdownMessage";
import type { Source, UsedMemory } from "@/lib/api";

vi.mock("shiki", () => ({
  createHighlighter: vi.fn(async () => {
    throw new Error("shiki unavailable in markdown fallback tests");
  }),
}));

const clipboardWriteText = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: {
    writeText: clipboardWriteText,
  },
});

beforeEach(() => {
  clipboardWriteText.mockClear();
});

const SOURCES: Source[] = [
  { id: "s1", filename: "a.pdf", source_label: "S1" },
  { id: "s2", filename: "b.pdf", source_label: "S2" },
  { id: "s4", filename: "d.pdf", source_label: "S4" },
];

const MEMS: UsedMemory[] = [
  { id: "m1", memory_label: "M1", content: "User likes brevity." },
  { id: "m2", memory_label: "M2", content: "User prefers citations." },
];

describe("parseCitationSegments - sparse [S#] labels", () => {
  it("preserves S2/S4 labels even though only those are cited", () => {
    const { segments, citedSources } = parseCitationSegments(
      "Per [S2] and [S4], we conclude.",
      SOURCES
    );
    const citationSegs = segments.filter((s) => s.type === "citation");
    expect(citationSegs.map((s) => s.sourceName)).toEqual(["S2", "S4"]);
    expect(citedSources.map((s) => s.id)).toEqual(["s2", "s4"]);
  });
});

describe("parseCitationSegments - [M#] memory citations", () => {
  it("recognizes memory labels distinct from source labels", () => {
    const { segments, citedSources, citedMemories } = parseCitationSegments(
      "Doc claim [S1] and memory [M1].",
      SOURCES,
      MEMS
    );
    const memSegs = segments.filter((s) => s.type === "memory_citation");
    expect(memSegs.map((s) => s.memoryLabel)).toEqual(["M1"]);
    expect(citedSources.map((s) => s.id)).toEqual(["s1"]);
    expect(citedMemories.map((m) => m.id)).toEqual(["m1"]);
  });

  it("does not look up memory M1 as document S1", () => {
    const { citedMemories, citedSources } = parseCitationSegments(
      "Memory says [M1].",
      SOURCES,
      MEMS
    );
    expect(citedMemories[0].memory_label).toBe("M1");
    expect(citedSources.length).toBe(0);
  });

  it("memory chip falls back gracefully when label unknown", () => {
    const { segments, citedMemories } = parseCitationSegments(
      "References [M9] unknown.",
      SOURCES,
      MEMS
    );
    const memSegs = segments.filter((s) => s.type === "memory_citation");
    expect(memSegs.length).toBe(1);
    expect(citedMemories.length).toBe(0);
  });
});

describe("parseCitationSegments - legacy [Source: name]", () => {
  it("still resolves filename-based citations", () => {
    const { citedSources } = parseCitationSegments(
      "See [Source: a.pdf] for details.",
      SOURCES
    );
    expect(citedSources.map((s) => s.id)).toEqual(["s1"]);
  });
});

describe("MarkdownMessage code rendering", () => {
  it("renders inline code without code-block copy controls", () => {
    render(<MarkdownMessage content="Run `npm test` before shipping." />);

    expect(screen.getByText("npm test").tagName).toBe("CODE");
    expect(screen.queryByLabelText("Copy code to clipboard")).not.toBeInTheDocument();
  });

  it("renders fenced code with a language badge and copy control", () => {
    render(<MarkdownMessage content={"```ts\nconst answer = 42;\n```"} />);

    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("const answer = 42;")).toBeInTheDocument();
    expect(screen.getByLabelText("Copy code to clipboard")).toBeInTheDocument();
  });

  it("renders fenced code without a language as a copyable code block", () => {
    render(<MarkdownMessage content={"```\nplain block\n```"} />);

    expect(screen.getByText("plain block")).toBeInTheDocument();
    expect(screen.getByLabelText("Copy code to clipboard")).toBeInTheDocument();
  });

  it("copies fenced code without the markdown parser trailing newline", async () => {
    render(<MarkdownMessage content={"```txt\nline one\nline two\n```"} />);

    fireEvent.click(screen.getByLabelText("Copy code to clipboard"));

    await waitFor(() => {
      expect(clipboardWriteText).toHaveBeenCalledWith("line one\nline two");
    });
  });

  it("escapes code when the Shiki fallback renderer is used", async () => {
    render(<MarkdownMessage content={'```html\n<img src=x onerror="alert(1)">\n```'} />);

    await waitFor(() => {
      expect(document.querySelector(".shiki-wrapper")).toBeInTheDocument();
    });
    expect(document.querySelector(".shiki-wrapper img")).not.toBeInTheDocument();
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
  });

  it("joins array code children without inserting commas", () => {
    expect(MarkdownMessageTestInternals.codeChildrenToText(["line1", "line2"])).toBe("line1line2");
  });
});
