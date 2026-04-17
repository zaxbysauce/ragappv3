import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { NavigationRail } from "./NavigationRail";
import type { NavItemId } from "./navigationTypes";

// Mock useThemeStore before importing NavigationRail (NavigationRail imports useThemeStore)
vi.mock("@/stores/useThemeStore", () => ({
  useThemeStore: vi.fn(() => "dark"),
  applyTheme: vi.fn(),
}));

// Mock health status
const mockHealthStatus = {
  backend: true,
  embeddings: true,
  chat: true,
  loading: false,
};

// Mock window.location.href for chatNew navigation
const mockLocation = { href: "" };
Object.defineProperty(window, "location", {
  value: mockLocation,
  writable: true,
});

describe("NavigationRail", () => {
  describe("Navigation Items", () => {
    it("renders all navigation items including chatNew", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      // Check for all expected nav items
      expect(screen.getByLabelText("Chat")).toBeInTheDocument();
      expect(screen.getByLabelText("Chat (New)")).toBeInTheDocument();
      expect(screen.getByLabelText("Documents")).toBeInTheDocument();
      expect(screen.getByLabelText("Memory")).toBeInTheDocument();
      expect(screen.getByLabelText("Vaults")).toBeInTheDocument();
      expect(screen.getByLabelText("Settings")).toBeInTheDocument();
    });

    it("renders chatNew with NEW badge", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      // Check for NEW badge on chatNew item
      const newBadge = screen.getByText("NEW");
      expect(newBadge).toBeInTheDocument();
      expect(newBadge).toHaveClass("bg-gradient-to-r", "from-purple-500", "to-pink-500");
    });

    it("renders chatNew with gradient styling", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      const chatNewButton = screen.getByLabelText("Chat (New)");
      expect(chatNewButton).toHaveClass("bg-gradient-to-br", "from-purple-500/10", "to-pink-500/10");
      expect(chatNewButton).toHaveClass("border", "border-purple-500/30");
    });

    it("renders chatNew icon with gradient background", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      const chatNewIconContainer = screen.getByLabelText("Chat (New)").querySelector("div");
      expect(chatNewIconContainer).toHaveClass("bg-gradient-to-br", "from-purple-500", "to-pink-500");
      expect(chatNewIconContainer).toHaveClass("text-white");
    });

    it("renders chatNew label with gradient text", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      // Get the visible label by querying the button and filtering out sr-only
      const chatNewButton = screen.getByLabelText("Chat (New)");
      const allLabels = chatNewButton.querySelectorAll("span");
      // The visible label is the one without sr-only class
      const visibleLabels = Array.from(allLabels).filter((span) => !span.classList.contains("sr-only"));
      const chatNewLabel = visibleLabels.find((span) => span.textContent === "Chat (New)");
      
      expect(chatNewLabel).toBeInTheDocument();
      expect(chatNewLabel).toHaveClass("bg-gradient-to-r", "from-purple-500", "to-pink-500");
      expect(chatNewLabel).toHaveClass("bg-clip-text", "text-transparent");
    });

    it("chatNew icon has pulse animation", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      const chatNewIcon = screen.getByLabelText("Chat (New)").querySelector("svg");
      expect(chatNewIcon).toHaveClass("animate-pulse");
    });
  });

  describe("Active State", () => {
    it("highlights active item with primary background", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      const chatButton = screen.getByLabelText("Chat");
      expect(chatButton).toHaveClass("bg-primary/10");
    });

    it("does not show active indicator on chatNew when active", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chatNew"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      // chatNew should NOT have the right-side active indicator
      const chatNewButton = screen.getByLabelText("Chat (New)");
      const activeIndicator = chatNewButton.querySelector("span.w-1.h-4");
      expect(activeIndicator).not.toBeInTheDocument();
    });
  });

  describe("Interactions", () => {
    it("calls onItemSelect for regular items", () => {
      const handleSelect = vi.fn<(id: NavItemId) => void>();

      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={handleSelect}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      const documentsButton = screen.getByLabelText("Documents");
      fireEvent.click(documentsButton);

      expect(handleSelect).toHaveBeenCalledWith("documents");
    });

    it("navigates to /chat/redesign for chatNew item", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      const chatNewButton = screen.getByLabelText("Chat (New)");
      fireEvent.click(chatNewButton);

      expect(window.location.href).toBe("/chat/redesign");
    });
  });

  describe("Health Status Footer", () => {
    it("renders health status indicators", () => {
      render(
        <MemoryRouter>
          <NavigationRail
            activeItem="chat"
            onItemSelect={vi.fn()}
            healthStatus={mockHealthStatus}
          />
        </MemoryRouter>
      );

      // Check for health status labels in the footer
      expect(screen.getByText("API")).toBeInTheDocument();
      expect(screen.getByText("Embeddings")).toBeInTheDocument();
      // The "Chat" text appears both in nav and health status, so use getAllByText
      const chatLabels = screen.getAllByText("Chat");
      expect(chatLabels.length).toBeGreaterThan(0);

      // Check green indicators (healthy) - look in the footer container by class
      const footerContainer = screen.getByText("API").closest("div");
      const greenIndicators = footerContainer.querySelectorAll(".bg-success");
      expect(greenIndicators.length).toBeGreaterThan(0);
    });
  });

  describe("TypeScript Types", () => {
    it("chatNew is a valid NavItemId", () => {
      // This test verifies the type is properly exported
      const validId: NavItemId = "chatNew";
      expect(validId).toBe("chatNew");
    });
  });
});
