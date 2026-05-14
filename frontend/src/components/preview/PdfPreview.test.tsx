/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PdfPreview from "./PdfPreview";

describe("PdfPreview", () => {
  it("renders non-PDF fallback as a real download link through Button asChild", () => {
    render(
      <PdfPreview
        blobUrl="blob:preview"
        filename="preview.html"
        isPdf={false}
      />
    );

    const link = screen.getByRole("link", { name: /download original/i });
    expect(link).toHaveAttribute("href", "blob:preview");
    expect(link).toHaveAttribute("download", "preview.html");
    expect(link).not.toHaveAttribute("target");
  });
});
