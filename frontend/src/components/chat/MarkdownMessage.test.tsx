import { describe, it, expect } from "vitest";
import { parseCitationSegments } from "./MarkdownMessage";
import type { Source, UsedMemory } from "@/lib/api";

const SOURCES: Source[] = [
  { id: "s1", filename: "a.pdf", source_label: "S1" },
  { id: "s2", filename: "b.pdf", source_label: "S2" },
  { id: "s4", filename: "d.pdf", source_label: "S4" },
];

const MEMS: UsedMemory[] = [
  { id: "m1", memory_label: "M1", content: "User likes brevity." },
  { id: "m2", memory_label: "M2", content: "User prefers citations." },
];

describe("parseCitationSegments — sparse [S#] labels", () => {
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

describe("parseCitationSegments — [M#] memory citations", () => {
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
    // Even when sources contain S1, [M1] resolves to the memory list.
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

describe("parseCitationSegments — legacy [Source: name]", () => {
  it("still resolves filename-based citations", () => {
    const { citedSources } = parseCitationSegments(
      "See [Source: a.pdf] for details.",
      SOURCES
    );
    expect(citedSources.map((s) => s.id)).toEqual(["s1"]);
  });
});
