/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RightPane } from "./RightPane";
import * as useChatStoreModule from "@/stores/useChatStore";
import * as useChatShellStoreModule from "@/stores/useChatShellStore";

// Mock @tanstack/react-virtual
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: vi.fn(() => ({
    getVirtualItems: vi.fn(() => [
      { index: 0, start: 0, size: 80, key: "source-0", measureElement: vi.fn() },
      { index: 1, start: 80, size: 80, key: "source-1", measureElement: vi.fn() },
    ]),
    getTotalSize: vi.fn(() => 160),
    measureElement: vi.fn(),
  })),
}));

// Mock the stores
vi.mock("@/stores/useChatStore", () => ({
  useChatStore: vi.fn(),
}));

vi.mock("@/stores/useChatShellStore", () => ({
  useChatShellStore: vi.fn(),
}));

// Mock UI components with proper interactivity
const mockOnValueChange = vi.fn();

vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({ children, value, onValueChange }: any) => {
    if (onValueChange) {
      mockOnValueChange.mockImplementation(onValueChange);
    }
    return (
      <div data-testid="tabs" data-value={value}>
        {children}
      </div>
    );
  },
  TabsList: ({ children }: any) => <div data-testid="tabs-list">{children}</div>,
  TabsTrigger: ({ children, value, disabled, onClick }: any) => (
    <button
      data-testid={`tab-${value}`}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  ),
  TabsContent: ({ children, value }: any) => (
    <div data-testid={`tab-content-${value}`}>{children}</div>
  ),
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: any) => <div data-testid="scroll-area">{children}</div>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, variant, size, ...props }: any) => (
    <button data-testid={props["data-testid"]} onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

const mockUseChatStore = useChatStoreModule.useChatStore as unknown as ReturnType<
  typeof vi.fn
>;

const mockUseChatShellStore = useChatShellStoreModule.useChatShellStore as unknown as ReturnType<
  typeof vi.fn
>;

// Test helpers
const createMockSource = (overrides = {}) => ({
  id: `source-${Math.random().toString(36).substr(2, 9)}`,
  filename: "test-document.pdf",
  snippet: "This is a test snippet for the document",
  score: 0.15,
  score_type: "distance" as const,
  ...overrides,
});

const createMockMessage = (overrides = {}) => ({
  id: `msg-${Math.random().toString(36).substr(2, 9)}`,
  role: "user" as const,
  content: "Test message content",
  ...overrides,
});

// Helper to create many sources
const createManySources = (count: number, startIndex = 0) =>
  Array.from({ length: count }, (_, i) =>
    createMockSource({
      id: `source-${startIndex + i}`,
      filename: `document-${startIndex + i}.pdf`,
      snippet: `Snippet for document ${startIndex + i}`,
      score: 0.1 + (i * 0.01),
      score_type: "distance" as const,
    })
  );

describe("RightPane virtualization", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockOnValueChange.mockClear();

    // Default store mocks
    mockUseChatStore.mockReturnValue({
      messages: [],
      expandedSources: new Set(),
    });

    mockUseChatShellStore.mockReturnValue({
      selectedEvidenceSource: null,
      setSelectedEvidenceSource: vi.fn(),
      activeRightTab: "evidence",
      setActiveRightTab: vi.fn(),
    });
  });

  // =============================================================================
  // BOUNDARY TESTS: 20 sources (non-virtualized) vs 21 sources (virtualized)
  // =============================================================================
  describe("virtualization boundary at 20/21 sources", () => {
    it("should NOT use virtualization with exactly 20 sources", () => {
      const sources = createManySources(20);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      // Should show ScrollArea within sources tab content (non-virtualized path)
      const sourcesContent = screen.getByTestId("tab-content-sources");
      const scrollArea = sourcesContent.querySelector('[data-testid="scroll-area"]');
      expect(scrollArea).toBeInTheDocument();
    });

    it("should use virtualization with exactly 21 sources", () => {
      const sources = createManySources(21);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      // Should show the virtualized container (overflow-y-auto div with aria-label)
      const virtualizedContainer = screen.getByLabelText("Sources list");
      expect(virtualizedContainer).toBeInTheDocument();
      expect(virtualizedContainer).toHaveClass("overflow-y-auto");
    });
  });

  // =============================================================================
  // EMPTY STATE: 0 sources
  // =============================================================================
  describe("empty state (0 sources)", () => {
    it("should show empty state message when no sources", () => {
      mockUseChatStore.mockReturnValue({
        messages: [],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      expect(
        screen.getByText("No sources available. Send a message to see retrieved sources.")
      ).toBeInTheDocument();
    });

    it("should not render ScrollArea or virtualized container when no sources", () => {
      mockUseChatStore.mockReturnValue({
        messages: [],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      const sourcesContent = screen.getByTestId("tab-content-sources");
      expect(sourcesContent.querySelector('[data-testid="scroll-area"]')).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Sources list")).not.toBeInTheDocument();
    });
  });

  // =============================================================================
  // NON-VIRTUALIZED PATH: <= 20 sources
  // =============================================================================
  describe("non-virtualized path (<= 20 sources)", () => {
    it("should render ScrollArea for 1 source", () => {
      const sources = [createMockSource({ id: "src-1", filename: "one.pdf" })];
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      const sourcesContent = screen.getByTestId("tab-content-sources");
      const scrollArea = sourcesContent.querySelector('[data-testid="scroll-area"]');
      expect(scrollArea).toBeInTheDocument();
    });

    it("should render ScrollArea for 10 sources", () => {
      const sources = createManySources(10);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      const sourcesContent = screen.getByTestId("tab-content-sources");
      const scrollArea = sourcesContent.querySelector('[data-testid="scroll-area"]');
      expect(scrollArea).toBeInTheDocument();
    });

    it("should render ScrollArea for 20 sources", () => {
      const sources = createManySources(20);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      const sourcesContent = screen.getByTestId("tab-content-sources");
      const scrollArea = sourcesContent.querySelector('[data-testid="scroll-area"]');
      expect(scrollArea).toBeInTheDocument();
    });

    it("should render all source items in non-virtualized list", () => {
      const sources = [
        createMockSource({ id: "src-1", filename: "first.pdf" }),
        createMockSource({ id: "src-2", filename: "second.pdf" }),
        createMockSource({ id: "src-3", filename: "third.pdf" }),
      ];
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      expect(screen.getByText("first.pdf")).toBeInTheDocument();
      expect(screen.getByText("second.pdf")).toBeInTheDocument();
      expect(screen.getByText("third.pdf")).toBeInTheDocument();
    });

    it("should render source count badge correctly for <= 20 sources", () => {
      const sources = createManySources(15);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      expect(screen.getByText("(15)")).toBeInTheDocument();
    });
  });

  // =============================================================================
  // VIRTUALIZED PATH: > 20 sources
  // =============================================================================
  describe("virtualized path (> 20 sources)", () => {
    it("should render virtualized container for 21 sources", () => {
      const sources = createManySources(21);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      const container = screen.getByLabelText("Sources list");
      expect(container).toBeInTheDocument();
      expect(container).toHaveClass("overflow-y-auto");
    });

    it("should render virtualized container for 50 sources", () => {
      const sources = createManySources(50);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      const container = screen.getByLabelText("Sources list");
      expect(container).toBeInTheDocument();
    });

    it("should render virtualized container for 100 sources", () => {
      const sources = createManySources(100);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      const container = screen.getByLabelText("Sources list");
      expect(container).toBeInTheDocument();
    });

    it("should render source count badge correctly for > 20 sources", () => {
      const sources = createManySources(50);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      expect(screen.getByText("(50)")).toBeInTheDocument();
    });

    it("should NOT render ScrollArea when virtualized", () => {
      const sources = createManySources(25);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      // ScrollArea should NOT be in the sources tab content (it's in the preview tab)
      const sourcesContent = screen.getByTestId("tab-content-sources");
      expect(sourcesContent.querySelector('[data-testid="scroll-area"]')).not.toBeInTheDocument();
    });
  });

  // =============================================================================
  // SOURCE CLICK WORKS IN BOTH PATHS
  // =============================================================================
  describe("source click functionality in both paths", () => {
    it("should handle source click in non-virtualized path (5 sources)", async () => {
      const sources = createManySources(5);
      const setSelectedEvidenceSource = vi.fn();
      const setActiveRightTab = vi.fn();

      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      mockUseChatShellStore.mockReturnValue({
        selectedEvidenceSource: null,
        setSelectedEvidenceSource,
        setActiveRightTab,
        activeRightTab: "evidence",
      });

      render(<RightPane />);

      const sourceButton = screen.getByText("document-0.pdf").closest("button");
      expect(sourceButton).toBeInTheDocument();

      if (sourceButton) {
        fireEvent.click(sourceButton);
      }

      await waitFor(() => {
        expect(setSelectedEvidenceSource).toHaveBeenCalledWith(sources[0]);
      });
    });

    it("should handle source click in virtualized path (25 sources)", async () => {
      const sources = createManySources(25);
      const setSelectedEvidenceSource = vi.fn();
      const setActiveRightTab = vi.fn();

      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources }),
        ],
        expandedSources: new Set(),
      });

      mockUseChatShellStore.mockReturnValue({
        selectedEvidenceSource: null,
        setSelectedEvidenceSource,
        setActiveRightTab,
        activeRightTab: "evidence",
      });

      render(<RightPane />);

      // The virtualized list renders items - we look for the source by filename
      // In virtualized mode, items may not all be in DOM but the click handler should work
      const sourceButtons = screen.getAllByText(/document-0\.pdf/);
      // There might be multiple matches if preview is also shown
      const sourceButton = sourceButtons[0]?.closest("button");
      expect(sourceButton).toBeInTheDocument();

      if (sourceButton) {
        fireEvent.click(sourceButton);
      }

      await waitFor(() => {
        expect(setSelectedEvidenceSource).toHaveBeenCalled();
      });
    });
  });

  // =============================================================================
  // EDGE CASES
  // =============================================================================
  describe("edge cases", () => {
    it("should handle exactly 0 sources", () => {
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources: [] }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      expect(
        screen.getByText("No sources available. Send a message to see retrieved sources.")
      ).toBeInTheDocument();
    });

    it("should handle sources with undefined/null values filtered out", () => {
      const sources = [
        createMockSource({ id: "src-1" }),
        // @ts-ignore - simulating filtered null
        null,
        createMockSource({ id: "src-3" }),
      ];
      // The component filters null sources, so we pass valid array after filter
      const validSources = sources.filter(Boolean);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources: validSources }),
        ],
        expandedSources: new Set(),
      });

      render(<RightPane />);

      // Should show 2 sources in count
      expect(screen.getByText("(2)")).toBeInTheDocument();
    });

    it("should handle switching from non-virtualized to virtualized count", () => {
      // First render with 5 sources (non-virtualized)
      const sources5 = createManySources(5);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources: sources5 }),
        ],
        expandedSources: new Set(),
      });

      const { rerender } = render(<RightPane />);
      const sourcesContent = screen.getByTestId("tab-content-sources");
      expect(sourcesContent.querySelector('[data-testid="scroll-area"]')).toBeInTheDocument();

      // Rerender with 25 sources (virtualized)
      const sources25 = createManySources(25);
      mockUseChatStore.mockReturnValue({
        messages: [
          createMockMessage({ role: "user", content: "test" }),
          createMockMessage({ role: "assistant", content: "response", sources: sources25 }),
        ],
        expandedSources: new Set(),
      });

      rerender(<RightPane />);
      expect(screen.getByLabelText("Sources list")).toBeInTheDocument();
    });
  });
});
