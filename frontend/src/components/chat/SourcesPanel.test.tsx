import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { SourcesPanel } from "./SourcesPanel";
import type { Source } from "@/lib/api";

// Mock the UI components to simplify testing and avoid Radix internal components
vi.mock("@/components/ui/card", () => ({
  Card: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="card" className={className}>{children}</div>
  ),
  CardHeader: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card-header">{children}</div>
  ),
  CardTitle: ({ children }: { children: React.ReactNode }) => (
    <h3 data-testid="card-title">{children}</h3>
  ),
  CardDescription: ({ children }: { children: React.ReactNode }) => (
    <p data-testid="card-description">{children}</p>
  ),
  CardContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card-content">{children}</div>
  ),
}));

vi.mock("@/components/ui/badge", () => ({
  Badge: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <span data-testid="badge" className={className}>{children}</span>
  ),
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="scroll-area">{children}</div>
  ),
}));

vi.mock("@/components/ui/accordion", () => ({
  Accordion: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="accordion">{children}</div>
  ),
  AccordionItem: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="accordion-item">{children}</div>
  ),
  AccordionTrigger: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="accordion-trigger">{children}</div>
  ),
  AccordionContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="accordion-content">{children}</div>
  ),
}));

describe("SourcesPanel", () => {
  const mockOnToggle = vi.fn();
  
  beforeEach(() => {
    mockOnToggle.mockClear();
  });

  // Helper to get the first badge (desktop version) since both desktop and mobile render
  const getFirstBadge = () => {
    const badges = screen.getAllByTestId("badge");
    return badges[0];
  };

  // ============================================
  // Rank number display tests
  // ============================================
  it("test_source_card_shows_rank_number — Render SourceCard with source={{score: 0.1}} and index=0, verify text contains '#1'", () => {
    const mockSources: Source[] = [
      {
        id: "test-source-1",
        filename: "test-document.pdf",
        snippet: "Test snippet content",
        score: 0.1,
        score_type: "distance",
      },
    ];

    render(
      <SourcesPanel
        sources={mockSources}
        expandedSources={new Set()}
        onToggleSource={mockOnToggle}
      />
    );

    // The badge should contain "#1" for rank
    const badge = getFirstBadge();
    expect(badge.textContent).toContain("#1");
  });

  // ============================================
  // No percentage display tests
  // ============================================
  it("test_source_card_shows_relevance_not_percentage — Render with score, verify the rendered text does NOT contain '%' character", () => {
    const mockSources: Source[] = [
      {
        id: "test-source-2",
        filename: "test-document.pdf",
        snippet: "Test snippet content",
        score: 0.15,
        score_type: "distance",
      },
    ];

    render(
      <SourcesPanel
        sources={mockSources}
        expandedSources={new Set()}
        onToggleSource={mockOnToggle}
      />
    );

    // Get the first badge specifically
    const badge = getFirstBadge();
    
    // Verify the badge specifically has no percentage
    expect(badge.textContent).not.toContain("%");
  });

  // ============================================
  // No score behavior tests
  // ============================================
  it("test_source_card_no_score_shows_no_badge — Render without score, verify no rank badge is shown", () => {
    const mockSources: Source[] = [
      {
        id: "test-source-3",
        filename: "test-document.pdf",
        snippet: "Test snippet content",
        // No score property
      } as Source,
    ];

    render(
      <SourcesPanel
        sources={mockSources}
        expandedSources={new Set()}
        onToggleSource={mockOnToggle}
      />
    );

    // When there's no score, the badge should not be rendered
    const badge = screen.queryByTestId("badge");
    expect(badge).toBeNull();
  });

  // ============================================
  // Verify relevance label text appears
  // ============================================
  it("test_source_card_displays_relevance_label_text", () => {
    const mockSources: Source[] = [
      {
        id: "test-source-5",
        filename: "test-document.pdf",
        snippet: "Test snippet content",
        score: 0.1, // Should be "Highly Relevant" for distance
        score_type: "distance",
      },
    ];

    render(
      <SourcesPanel
        sources={mockSources}
        expandedSources={new Set()}
        onToggleSource={mockOnToggle}
      />
    );

    const badge = getFirstBadge();
    expect(badge.textContent).toContain("Highly Relevant");
  });

  // ============================================
  // Verify different score types show correct labels
  // ============================================
  it("test_source_card_shows_rerank_label_correctly", () => {
    const mockSources: Source[] = [
      {
        id: "test-source-6",
        filename: "test-document.pdf",
        snippet: "Test snippet content",
        score: 0.8, // Should be "Highly Relevant" for rerank
        score_type: "rerank",
      },
    ];

    render(
      <SourcesPanel
        sources={mockSources}
        expandedSources={new Set()}
        onToggleSource={mockOnToggle}
      />
    );

    const badge = getFirstBadge();
    expect(badge.textContent).toContain("Highly Relevant");
  });

  it("test_source_card_shows_rrf_label_correctly", () => {
    const mockSources: Source[] = [
      {
        id: "test-source-7",
        filename: "test-document.pdf",
        snippet: "Test snippet content",
        score: 0.6, // Should be "Top Match" for rrf
        score_type: "rrf",
      },
    ];

    render(
      <SourcesPanel
        sources={mockSources}
        expandedSources={new Set()}
        onToggleSource={mockOnToggle}
      />
    );

    const badge = getFirstBadge();
    expect(badge.textContent).toContain("Top Match");
  });

  // ============================================
  // Additional verification: rank increments correctly for multiple sources
  // ============================================
  it("test_source_card_shows_correct_rank_for_multiple_sources", () => {
    const mockSources: Source[] = [
      {
        id: "test-source-a",
        filename: "document-a.pdf",
        snippet: "Content A",
        score: 0.1,
        score_type: "distance",
      },
      {
        id: "test-source-b",
        filename: "document-b.pdf",
        snippet: "Content B",
        score: 0.2,
        score_type: "distance",
      },
      {
        id: "test-source-c",
        filename: "document-c.pdf",
        snippet: "Content C",
        score: 0.3,
        score_type: "distance",
      },
    ];

    render(
      <SourcesPanel
        sources={mockSources}
        expandedSources={new Set()}
        onToggleSource={mockOnToggle}
      />
    );

    // All badges should be present (desktop + mobile = 6 total)
    const badges = screen.getAllByTestId("badge");
    expect(badges).toHaveLength(6); // 3 sources × 2 (desktop + mobile)

    // Verify desktop badges have ranks #1, #2, #3 (first 3 are desktop)
    expect(badges[0].textContent).toContain("#1");
    expect(badges[1].textContent).toContain("#2");
    expect(badges[2].textContent).toContain("#3");
    
    // Mobile badges (last 3) should also have ranks
    expect(badges[3].textContent).toContain("#1");
    expect(badges[4].textContent).toContain("#2");
    expect(badges[5].textContent).toContain("#3");
  });
});
