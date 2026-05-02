import { describe, it, expect } from "vitest";
import { getSourceBadgeLabel } from "./SourceCards";
import type { Source } from "@/lib/api";

describe("getSourceBadgeLabel", () => {
  it("renders the stable source_label when present (S2 != 1)", () => {
    const source: Source = {
      id: "x",
      filename: "x.pdf",
      source_label: "S2",
    };
    expect(getSourceBadgeLabel(source, 0)).toBe("S2");
  });

  it("renders S4 even when displayed first in the list", () => {
    const source: Source = {
      id: "y",
      filename: "y.pdf",
      source_label: "S4",
    };
    // fallbackIndex would naively show "S1" — we must not fall back.
    expect(getSourceBadgeLabel(source, 0)).toBe("S4");
  });

  it("falls back to ordinal label when source_label missing", () => {
    const source: Source = { id: "z", filename: "z.pdf" };
    expect(getSourceBadgeLabel(source, 0)).toBe("S1");
    expect(getSourceBadgeLabel(source, 2)).toBe("S3");
  });

  it("ignores empty/whitespace source_label", () => {
    const source: Source = {
      id: "z",
      filename: "z.pdf",
      source_label: "  ",
    };
    expect(getSourceBadgeLabel(source, 0)).toBe("S1");
  });
});
