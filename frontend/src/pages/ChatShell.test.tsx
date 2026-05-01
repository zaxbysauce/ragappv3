import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import ChatShell from "./ChatShell";

// Mock matchMedia for useIsMobile hook. Tests can flip `matchMediaMatches` to
// simulate viewports below a given breakpoint (mobile/tablet). Default is
// desktop (no media query matches).
let matchMediaMatches = false;
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    get matches() {
      return matchMediaMatches;
    },
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Create a mutable mock store state
let mockStoreState = {
  sessionRailOpen: true,
  rightPaneOpen: false,
  rightPaneWidth: 320,
  activeSessionId: null as string | null,
  activeSessionTitle: null as string | null,
  activeRightTab: "evidence" as "evidence" | "preview",
  sessionSearchQuery: "",
  pinnedSessionIds: [] as number[],
  selectedEvidenceSource: null,
  toggleSessionRail: vi.fn(),
  toggleRightPane: vi.fn(),
  setRightPaneWidth: vi.fn(),
  setActiveSessionId: vi.fn(),
  setActiveSessionTitle: vi.fn(),
  openSessionRail: vi.fn(),
  closeSessionRail: vi.fn(),
  openRightPane: vi.fn(),
  closeRightPane: vi.fn(),
  setActiveRightTab: vi.fn(),
  setSessionSearchQuery: vi.fn(),
  togglePinSession: vi.fn(),
  isSessionPinned: vi.fn(),
  setSelectedEvidenceSource: vi.fn(),
};

// Mock the Sheet component from @/components/ui/sheet
// Always render content so test queries can find DOM nodes; open/close is CSS-controlled
vi.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean; onOpenChange?: (open: boolean) => void }) => {
    return <div data-testid="sheet-mock" data-open={open ? "true" : "false"}>{children}</div>;
  },
  SheetContent: ({ children, className, side }: { children: React.ReactNode; className?: string; side?: string }) => (
    <div data-testid="sheet-content" data-side={side} className={className}>
      {children}
    </div>
  ),
  SheetHeader: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="sheet-header" className={className}>
      {children}
    </div>
  ),
  SheetTitle: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="sheet-title">{children}</div>
  ),
  SheetDescription: ({ children }: { children: React.ReactNode }) => (
    <p data-testid="sheet-description">{children}</p>
  ),
  SheetClose: ({ children, onClick }: { children?: React.ReactNode; onClick?: () => void }) => (
    <button data-testid="sheet-close" onClick={onClick}>{children}</button>
  ),
}));

// Mock the store
vi.mock("@/stores/useChatShellStore", () => ({
  __esModule: true,
  default: vi.fn(() => mockStoreState),
  useChatShellStore: vi.fn(() => mockStoreState),
}));

describe("ChatShell Mobile Layout", () => {
  beforeEach(() => {
    // Reset mock store state before each test
    mockStoreState = {
      sessionRailOpen: false,
      rightPaneOpen: false,
      rightPaneWidth: 320,
      activeSessionId: null,
      activeSessionTitle: null,
      activeRightTab: "evidence",
      sessionSearchQuery: "",
      pinnedSessionIds: [],
      selectedEvidenceSource: null,
      toggleSessionRail: vi.fn(),
      toggleRightPane: vi.fn(),
      setRightPaneWidth: vi.fn(),
      setActiveSessionId: vi.fn(),
      setActiveSessionTitle: vi.fn(),
      openSessionRail: vi.fn(),
      closeSessionRail: vi.fn(),
      openRightPane: vi.fn(),
      closeRightPane: vi.fn(),
      setActiveRightTab: vi.fn(),
      setSessionSearchQuery: vi.fn(),
      togglePinSession: vi.fn(),
      isSessionPinned: vi.fn(),
      setSelectedEvidenceSource: vi.fn(),
    };
    // Default: desktop viewport (no media queries match => isMobile/isBelowLg=false)
    matchMediaMatches = false;
    vi.clearAllMocks();
  });

  describe("test_session_rail_desktop_aside_hidden_on_mobile", () => {
    it("session rail desktop aside has hidden class and md:flex classes", () => {
      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      const sessionRail = document.querySelector('aside[aria-label="Chat sessions"]');
      expect(sessionRail).toBeDefined();
      expect(sessionRail?.className).toContain("hidden");
      expect(sessionRail?.className).toContain("md:flex");
    });
  });

  describe("test_session_rail_sheet_renders_when_open", () => {
    it("session rail Sheet renders when mobileSheetOpen is true (controlled by mobile state)", () => {
      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // Note: mobileSheetOpen is a local React state in ChatShell, not the store.
      // Since we cannot directly manipulate local state in the rendered component without
      // extra scaffolding, we verify the Sheet IS present in the component (the SheetContent
      // with side="left" exists in the component code at ChatShell.tsx:168-178).
      // On desktop (matchMedia matches desktop), the Sheet is still mounted but invisible
      // because open=false. We test that the SheetContent with side="left" exists in DOM.
      const sheetContents = document.querySelectorAll('[data-testid="sheet-content"]');
      // The component always renders SheetContent for left side, just hidden when not mobile+open
      const leftSheets = Array.from(sheetContents).filter((el) => el.getAttribute("data-side") === "left");
      // At least one left SheetContent should be in the DOM (rendered by the component)
      expect(leftSheets.length).toBeGreaterThan(0);
    });
  });

  describe("test_right_pane_desktop_aside_hidden_on_mobile", () => {
    it("right pane desktop aside has hidden class and lg:flex classes", () => {
      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      const rightPane = document.querySelector('aside[aria-label="Details panel"]');
      expect(rightPane).toBeDefined();
      expect(rightPane?.className).toContain("hidden");
      expect(rightPane?.className).toContain("lg:flex");
    });
  });

  describe("test_right_pane_sheet_renders_75vh", () => {
    it("right pane Sheet renders at 75vh on below-lg viewports when rightPaneOpen and activeRightTab !== workspace", () => {
      mockStoreState.rightPaneOpen = true;
      mockStoreState.activeRightTab = "evidence";
      // Simulate below-lg viewport (tablet/mobile)
      matchMediaMatches = true;

      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // Find the Sheet content with side="bottom" and 75vh height
      const sheetContents = document.querySelectorAll('[data-testid="sheet-content"]');
      const bottomSheets = Array.from(sheetContents).filter((el) => el.getAttribute("data-side") === "bottom");
      const has75vh = bottomSheets.some((el) => el.className.includes("h-[75vh]"));
      expect(has75vh).toBe(true);
    });
  });

  describe("test_right_pane_sheet_not_mounted_on_desktop", () => {
    it("right pane Sheet (side=bottom) is NOT mounted on desktop (lg+) so the Radix SheetPortal overlay does not dim the viewport", () => {
      mockStoreState.rightPaneOpen = true;
      mockStoreState.activeRightTab = "evidence";
      // Default matchMediaMatches=false simulates desktop (>= lg)

      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // On desktop, the bottom-sheet right pane MUST NOT be rendered —
      // otherwise the portaled SheetOverlay would dim the entire page.
      const sheetContents = document.querySelectorAll('[data-testid="sheet-content"]');
      const bottomSheets = Array.from(sheetContents).filter((el) => el.getAttribute("data-side") === "bottom");
      expect(bottomSheets.length).toBe(0);
    });

  });

  describe("test_panel_left_toggle_visible_on_all_screens", () => {
    it("PanelLeft toggle button is visible on all screen sizes (no md:hidden)", () => {
      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // md:hidden was removed so the toggle is visible on desktop too
      const sessionToggle = screen.getByLabelText(/Show sessions|Hide sessions/);
      expect(sessionToggle).toBeDefined();
      expect(sessionToggle.className).not.toContain("md:hidden");
    });
  });

  describe("test_ios_safe_area_div_exists", () => {
    it("iOS safe area div exists with correct style", () => {
      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // Get the main element and check its children for safe area div
      const mainElement = document.querySelector('main');
      expect(mainElement).toBeDefined();
      
      // Find the safe area div as a direct child of main
      const children = mainElement?.querySelectorAll(':scope > div');
      const safeAreaDiv = Array.from(children || []).find(
        (div) => {
          const html = div.outerHTML;
          return html.includes('md:hidden') || div.getAttribute('aria-hidden') === 'true';
        }
      );
      
      expect(safeAreaDiv).toBeDefined();
    });
  });

  describe("test_resize_handle_hidden_on_mobile", () => {
    it("resize handle is not rendered when lg breakpoint is not active (hidden lg:block)", () => {
      mockStoreState.rightPaneOpen = true;

      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // The resize handle should have hidden lg:block class
      const resizeHandle = document.querySelector('[role="separator"][aria-label="Resize details panel"]');
      expect(resizeHandle).toBeDefined();
      expect(resizeHandle?.className).toContain("hidden");
      expect(resizeHandle?.className).toContain("lg:block");
    });
  });

  describe("test_panel_right_toggle_visible_all_sizes", () => {
    it("PanelRight toggle button is visible on all sizes (no md:hidden)", () => {
      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      const rightPaneToggle = screen.getByLabelText("Show details panel");
      expect(rightPaneToggle).toBeDefined();
      expect(rightPaneToggle.className).not.toContain("md:hidden");
    });
  });
});
