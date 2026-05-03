import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WikiCards, WikiCard } from "./WikiCards";
import type { WikiReference } from "@/lib/api";

const makeWiki = (overrides: Partial<WikiReference> = {}): WikiReference => ({
  wiki_label: "W1",
  page_id: 1,
  claim_id: 10,
  title: "Task Force Alpha",
  slug: "task-force-alpha",
  page_type: "entity",
  claim_text: "Task Force Alpha is responsible for regional operations.",
  excerpt: null,
  confidence: 0.9,
  status: "active",
  page_status: "verified",
  claim_status: "active",
  score: 0.85,
  score_type: "fts",
  source_count: 3,
  provenance_summary: "3 documents",
  ...overrides,
});

describe("WikiCards", () => {
  it("renders nothing when wikiRefs is empty", () => {
    const { container } = render(<WikiCards wikiRefs={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when wikiRefs is undefined-like (null cast)", () => {
    const { container } = render(<WikiCards wikiRefs={null as unknown as WikiReference[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders wiki-cards container with entries", () => {
    render(<WikiCards wikiRefs={[makeWiki()]} />);
    expect(screen.getByTestId("wiki-cards")).toBeInTheDocument();
    expect(screen.getByText("Wiki knowledge:")).toBeInTheDocument();
  });

  it("renders a card for each wiki ref", () => {
    render(
      <WikiCards
        wikiRefs={[
          makeWiki({ wiki_label: "W1", title: "Page One" }),
          makeWiki({ wiki_label: "W2", title: "Page Two" }),
        ]}
      />
    );
    expect(screen.getByLabelText("Wiki W1: Page One")).toBeInTheDocument();
    expect(screen.getByLabelText("Wiki W2: Page Two")).toBeInTheDocument();
  });
});

describe("WikiCard", () => {
  it("renders wiki label badge", () => {
    render(<WikiCard wikiRef={makeWiki({ wiki_label: "W3" })} />);
    expect(screen.getByLabelText("Wiki label W3")).toBeInTheDocument();
  });

  it("renders title", () => {
    render(<WikiCard wikiRef={makeWiki({ title: "AFOMIS Overview" })} />);
    expect(screen.getByText("AFOMIS Overview")).toBeInTheDocument();
  });

  it("renders page_type", () => {
    render(<WikiCard wikiRef={makeWiki({ page_type: "process" })} />);
    expect(screen.getByText("process")).toBeInTheDocument();
  });

  it("renders confidence percentage", () => {
    render(<WikiCard wikiRef={makeWiki({ confidence: 0.87 })} />);
    expect(screen.getByText("87%")).toBeInTheDocument();
  });

  it("renders claim_status when present", () => {
    render(<WikiCard wikiRef={makeWiki({ claim_status: "verified", page_status: "draft" })} />);
    expect(screen.getByText("verified")).toBeInTheDocument();
  });

  it("falls back to page_status when claim_status is null", () => {
    render(<WikiCard wikiRef={makeWiki({ claim_status: null, page_status: "stale" })} />);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("renders claim_text as body", () => {
    render(<WikiCard wikiRef={makeWiki({ claim_text: "The chief is Col Smith." })} />);
    expect(screen.getByText("The chief is Col Smith.")).toBeInTheDocument();
  });

  it("falls back to excerpt when claim_text is null", () => {
    render(<WikiCard wikiRef={makeWiki({ claim_text: null, excerpt: "From the excerpt." })} />);
    expect(screen.getByText("From the excerpt.")).toBeInTheDocument();
  });

  it("renders provenance_summary", () => {
    render(<WikiCard wikiRef={makeWiki({ provenance_summary: "5 documents" })} />);
    expect(screen.getByText("5 documents")).toBeInTheDocument();
  });

  it("renders external link button when slug is present", () => {
    render(<WikiCard wikiRef={makeWiki({ slug: "task-force-alpha" })} />);
    expect(screen.getByLabelText("Open wiki page Task Force Alpha")).toBeInTheDocument();
  });

  it("does not render external link button when slug is null", () => {
    render(<WikiCard wikiRef={makeWiki({ slug: null })} />);
    expect(screen.queryByRole("button", { name: /open wiki page/i })).not.toBeInTheDocument();
  });

  it("opens wiki page in new tab when external link is clicked", () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<WikiCard wikiRef={makeWiki({ slug: "task-force-alpha" })} />);
    fireEvent.click(screen.getByLabelText("Open wiki page Task Force Alpha"));
    expect(openSpy).toHaveBeenCalledWith(
      "/wiki?page=task-force-alpha",
      "_blank",
      "noopener"
    );
    openSpy.mockRestore();
  });

  it("truncates long body and shows More button", () => {
    const longText = "A".repeat(200);
    render(<WikiCard wikiRef={makeWiki({ claim_text: longText })} />);
    expect(screen.getByRole("button", { name: /more/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /less/i })).not.toBeInTheDocument();
  });

  it("expands long body on More click", () => {
    const longText = "A".repeat(200);
    render(<WikiCard wikiRef={makeWiki({ claim_text: longText })} />);
    fireEvent.click(screen.getByRole("button", { name: /more/i }));
    expect(screen.getByRole("button", { name: /less/i })).toBeInTheDocument();
    expect(screen.getByText(longText)).toBeInTheDocument();
  });

  it("does not show More button for short body", () => {
    render(<WikiCard wikiRef={makeWiki({ claim_text: "Short." })} />);
    expect(screen.queryByRole("button", { name: /more/i })).not.toBeInTheDocument();
  });
});
