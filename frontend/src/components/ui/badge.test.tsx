import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "./badge";

describe("Badge", () => {
  it("renders as span element", () => {
    render(<Badge>Test</Badge>);
    const badge = screen.getByText("Test");
    expect(badge.tagName).toBe("SPAN");
  });

  it("accepts variant prop", () => {
    render(<Badge variant="destructive">Test</Badge>);
    const badge = screen.getByText("Test");
    expect(badge).toHaveClass("bg-destructive");
  });

  it("spreads className correctly", () => {
    render(<Badge className="custom-class">Test</Badge>);
    const badge = screen.getByText("Test");
    expect(badge).toHaveClass("custom-class");
  });
});
