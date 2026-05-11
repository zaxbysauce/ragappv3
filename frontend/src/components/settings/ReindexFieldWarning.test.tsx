import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReindexFieldWarning } from "./ReindexFieldWarning";

describe("ReindexFieldWarning", () => {
  it("renders the default warning text", () => {
    render(<ReindexFieldWarning />);
    expect(
      screen.getByText(
        /Changing this requires re-indexing existing documents/i,
      ),
    ).toBeInTheDocument();
  });

  it("renders a custom message when provided", () => {
    render(<ReindexFieldWarning message="Custom warning text." />);
    expect(screen.getByText("Custom warning text.")).toBeInTheDocument();
  });

  it("has role=note for assistive tech", () => {
    render(<ReindexFieldWarning />);
    expect(screen.getByRole("note")).toBeInTheDocument();
  });
});
