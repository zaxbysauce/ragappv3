import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import ChatShell from "./ChatShell";

// Create a mutable mock store state
let mockStoreState = {
  sessionRailOpen: true,
  rightPaneOpen: false,
  rightPaneWidth: 320,
  activeSessionId: null as string | null,
  activeRightTab: "evidence" as "evidence" | "preview" | "workspace",
  sessionSearchQuery: "",
  pinnedSessionIds: [] as number[],
  selectedEvidenceSource: null,
  toggleSessionRail: vi.fn(),
  toggleRightPane: vi.fn(),
  setRightPaneWidth: vi.fn(),
  setActiveSessionId: vi.fn(),
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
vi.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children, open, onOpenChange }: { children: React.ReactNode; open?: boolean; onOpenChange?: (open: boolean) => void }) => {
    if (!open) return null;
    return <div data-testid="sheet-mock" data-open="true">{children}</div>;
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
      activeRightTab: "evidence",
      sessionSearchQuery: "",
      pinnedSessionIds: [],
      selectedEvidenceSource: null,
      toggleSessionRail: vi.fn(),
      toggleRightPane: vi.fn(),
      setRightPaneWidth: vi.fn(),
      setActiveSessionId: vi.fn(),
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
    it("session rail Sheet renders when sessionRailOpen is true", () => {
      mockStoreState.sessionRailOpen = true;

      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // Find the Sheet mock with side="left"
      const sheetContents = document.querySelectorAll('[data-testid="sheet-content"]');
      const leftSheet = Array.from(sheetContents).find((el) => el.getAttribute("data-side") === "left");
      expect(leftSheet).toBeDefined();
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
    it("right pane Sheet renders at 75vh when rightPaneOpen and activeRightTab !== workspace", () => {
      mockStoreState.rightPaneOpen = true;
      mockStoreState.activeRightTab = "evidence";

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

  describe("test_right_pane_sheet_renders_95vh_for_workspace", () => {
    it("right pane Sheet renders at 95vh when activeRightTab === workspace and rightPaneOpen", () => {
      mockStoreState.rightPaneOpen = true;
      mockStoreState.activeRightTab = "workspace";

      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // Find the Sheet content with side="bottom" and 95vh height
      const sheetContents = document.querySelectorAll('[data-testid="sheet-content"]');
      const bottomSheets = Array.from(sheetContents).filter((el) => el.getAttribute("data-side") === "bottom");
      const has95vh = bottomSheets.some((el) => el.className.includes("h-[95vh]"));
      expect(has95vh).toBe(true);
    });
  });

  describe("test_panel_left_toggle_has_md_hidden", () => {
    it("PanelLeft toggle button has md:hidden class", () => {
      render(
        <BrowserRouter>
          <ChatShell />
        </BrowserRouter>
      );

      // Find the toggle button with "Hide sessions" or "Show sessions" label
      const sessionToggle = screen.getByLabelText(/Show sessions|Hide sessions/);
      expect(sessionToggle).toBeDefined();
      expect(sessionToggle.className).toContain("md:hidden");
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
