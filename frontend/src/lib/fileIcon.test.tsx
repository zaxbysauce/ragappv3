import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { FileIcon } from "./fileIcon";

function renderIcon(filename: string | null | undefined) {
  const { container } = render(<FileIcon filename={filename} className="h-4 w-4" />);
  const svg = container.querySelector("svg");
  if (!svg) throw new Error("expected FileIcon to render an svg");
  return svg;
}

describe("FileIcon", () => {
  it("renders a red PDF icon and normalizes uppercase extensions", () => {
    const svg = renderIcon("REPORT.PDF");

    expect(svg).toHaveClass("h-4", "w-4");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveStyle({ color: "#ef4444" });
  });

  it.each([
    ["proposal.doc", "#3b82f6"],
    ["proposal.docx", "#3b82f6"],
    ["notes.md", "#14b8a6"],
    ["notes.mdx", "#14b8a6"],
    ["budget.xlsx", "#22c55e"],
    ["budget.xls", "#22c55e"],
    ["export.csv", "#22c55e"],
  ])("renders the expected colored branch for %s", (filename, color) => {
    expect(renderIcon(filename)).toHaveStyle({ color });
  });

  it("renders the neutral text icon branch for txt files", () => {
    const svg = renderIcon("readme.txt");

    expect(svg).toHaveClass("lucide-file-text");
    expect(svg.getAttribute("style") ?? "").not.toContain("color:");
  });

  it.each([null, undefined, "", "README", "archive.unknown"])(
    "falls back to the generic file icon for %s",
    (filename) => {
      const svg = renderIcon(filename);

      expect(svg).toHaveClass("lucide-file");
      expect(svg.getAttribute("style") ?? "").not.toContain("color:");
    }
  );
});
