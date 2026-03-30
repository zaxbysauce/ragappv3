// frontend/src/components/chat/SessionRail.adversarial.test.tsx
// ADVERSARIAL TESTS: Security, edge cases, race conditions, and attack vectors
// These tests deliberately try to break the component with malicious inputs

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { SessionRail, SessionItem } from "./SessionRail";
import * as api from "@/lib/api";
import * as useChatShellStoreModule from "@/stores/useChatShellStore";

// Set longer timeout for async tests
const TEST_TIMEOUT = 10000;

// Mock ResizeObserver for Radix UI components
beforeAll(() => {
  // @ts-ignore
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

// =============================================================================
// MOCKS
// =============================================================================

vi.mock("@/lib/api", () => ({
  listChatSessions: vi.fn(),
  deleteChatSession: vi.fn(),
  updateChatSession: vi.fn(),
  getChatSession: vi.fn(),
}));

const mockTogglePinSession = vi.fn();
const mockIsSessionPinned = vi.fn();
const mockSetSessionSearchQuery = vi.fn();
const mockSetActiveSessionId = vi.fn();

const createMockStore = (overrides = {}) => ({
  sessionRailOpen: true,
  rightPaneOpen: false,
  rightPaneWidth: 320,
  activeSessionId: null,
  sessionSearchQuery: "",
  pinnedSessionIds: [],
  toggleSessionRail: vi.fn(),
  toggleRightPane: vi.fn(),
  setRightPaneWidth: vi.fn(),
  setActiveSessionId: mockSetActiveSessionId,
  openSessionRail: vi.fn(),
  closeSessionRail: vi.fn(),
  openRightPane: vi.fn(),
  closeRightPane: vi.fn(),
  setSessionSearchQuery: mockSetSessionSearchQuery,
  togglePinSession: mockTogglePinSession,
  isSessionPinned: mockIsSessionPinned,
  ...overrides,
});

vi.mock("@/stores/useChatShellStore", () => ({
  useChatShellStore: vi.fn(),
}));

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

// =============================================================================
// ADVERSARIAL TEST SUITE
// =============================================================================

describe("SessionRail ADVERSARIAL TESTS", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useChatShellStoreModule.useChatShellStore).mockReturnValue(createMockStore());
  });

  // ===========================================================================
  // 1. XSS INJECTION IN SESSION TITLES
  // ===========================================================================
  describe("XSS Injection in session titles", () => {
    const xssPayloads = [
      '<img onerror="alert(1)" src=x>',
      '<script>alert("xss")</script>',
      '<svg onload="alert(1)">',
      '"><script>alert(document.cookie)</script>',
      '<a href="javascript:alert(1)">Click</a>',
      '<div onclick="alert(1)">click me</div>',
      '<iframe src="javascript:alert(1)"></iframe>',
      '${alert(1)}',
      '{{constructor.constructor("alert(1)")()}}',
    ];

    it.each(xssPayloads)("should NOT execute XSS payload: %s", async (payload) => {
      const maliciousSession = {
        id: 1,
        vault_id: 1,
        title: payload,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 1,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [maliciousSession] });

      // Spy on console.error to catch any script execution
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText((content) => content.includes(payload))).toBeInTheDocument();
      }, { timeout: TEST_TIMEOUT });

      // Verify no alerts or console errors from XSS attempt
      expect(consoleSpy).not.toHaveBeenCalledWith(
        expect.stringContaining("alert"),
        expect.anything()
      );

      consoleSpy.mockRestore();
    }, TEST_TIMEOUT);

    it("should NOT create script elements when title contains script tags", async () => {
      const maliciousSession = {
        id: 1,
        vault_id: 1,
        title: '<script>alert("xss")</script>Hello World',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 1,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [maliciousSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/<script>alert/)).toBeInTheDocument();
      });

      // Verify no script element was created
      expect(document.querySelector("script")).toBeNull();
    });

    it("should escape HTML entities in delete confirmation dialog", async () => {
      const maliciousSession = {
        id: 1,
        vault_id: 1,
        title: '<script>alert(1)</script>Test Session',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 1,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [maliciousSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Session/)).toBeInTheDocument();
      });

      const sessionItem = await screen.findByRole("button", { name: /chat session/i });
      fireEvent.mouseEnter(sessionItem);
      fireEvent.click(within(sessionItem).getByLabelText("Delete session"));

      await waitFor(() => {
        expect(screen.getByRole("dialog")).toBeInTheDocument();
      });

      const dialog = screen.getByRole("dialog");
      expect(dialog.textContent).toContain("Test Session");
      expect(dialog.innerHTML).not.toContain("<script>");
    });
  });

  // ===========================================================================
  // 2. RAPID PIN/UNPIN TOGGLING
  // ===========================================================================
  describe("Rapid pin/unpin toggling", () => {
    it("should maintain state consistency when pin is toggled rapidly", async () => {
      const mockSession = {
        id: 1,
        vault_id: 1,
        title: "Test Session",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [mockSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Test Session")).toBeInTheDocument();
      });

      const sessionItem = screen.getByRole("button", { name: /chat session/i });
      fireEvent.mouseEnter(sessionItem);

      const pinButton = within(sessionItem).getByLabelText("Pin session");

      // Rapidly click pin 10 times
      for (let i = 0; i < 10; i++) {
        fireEvent.click(pinButton);
      }

      expect(mockTogglePinSession).toHaveBeenCalledTimes(10);
    });
  });

  // ===========================================================================
  // 3 & 4. RAPID RENAME & DELETE DURING RENAME
  // ===========================================================================
  describe("Rapid rename and delete interactions", () => {
    it("should handle rapid keystrokes during rename", async () => {
      const mockSession = {
        id: 1,
        vault_id: 1,
        title: "Test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      const onRename = vi.fn();

      render(
        <Wrapper>
          <SessionItem
            session={mockSession}
            isActive={false}
            isPinned={false}
            onClick={vi.fn()}
            onRename={onRename}
            onPinToggle={vi.fn()}
            onDelete={vi.fn()}
          />
        </Wrapper>
      );

      const sessionElement = screen.getByRole("button", { name: /chat session/i });
      fireEvent.mouseEnter(sessionElement);
      fireEvent.click(screen.getByLabelText("Rename session"));

      await act(async () => {
        vi.runAllTimersAsync();
      });

      const input = screen.getByLabelText("Edit session title");

      // Rapidly type
      await act(async () => {
        for (let i = 0; i < 50; i++) {
          fireEvent.change(input, { target: { value: "A".repeat(i + 1) } });
        }
      });

      expect(input).toBeInTheDocument();
    });
  });

  // ===========================================================================
  // 5. NAVIGATE DURING FETCH
  // ===========================================================================
  describe("Navigate during fetch", () => {
    it("should handle session click while loading and after load", async () => {
      const mockSessions = [
        {
          id: 1,
          vault_id: 1,
          title: "Test Session",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 5,
        },
      ];

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: mockSessions });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Test Session")).toBeInTheDocument();
      });

      const sessionItem = screen.getByRole("button", { name: /chat session/i });
      fireEvent.click(sessionItem);

      expect(mockSetActiveSessionId).toHaveBeenCalledWith("1");
    });
  });

  // ===========================================================================
  // 6. VERY LONG TITLES
  // ===========================================================================
  describe("Very long session titles", () => {
    it("should truncate titles longer than 40 characters", async () => {
      const longTitle = "A".repeat(500);
      const mockSession = {
        id: 1,
        vault_id: 1,
        title: longTitle,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [mockSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        const expectedTruncated = "A".repeat(40) + "...";
        expect(screen.getByText(expectedTruncated)).toBeInTheDocument();
      });
    });

    it("should handle editing extremely long titles", async () => {
      const longTitle = "A".repeat(500);
      const mockSession = {
        id: 1,
        vault_id: 1,
        title: longTitle,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      const onRename = vi.fn();

      render(
        <Wrapper>
          <SessionItem
            session={mockSession}
            isActive={false}
            isPinned={false}
            onClick={vi.fn()}
            onRename={onRename}
            onPinToggle={vi.fn()}
            onDelete={vi.fn()}
          />
        </Wrapper>
      );

      const sessionElement = screen.getByRole("button", { name: /chat session/i });
      fireEvent.mouseEnter(sessionElement);
      fireEvent.click(screen.getByLabelText("Rename session"));

      await act(async () => {
        vi.runAllTimersAsync();
      });

      const input = screen.getByLabelText("Edit session title");
      expect(input).toHaveValue(longTitle);
    });
  });

  // ===========================================================================
  // 7. SPECIAL CHARACTERS IN SEARCH
  // ===========================================================================
  describe("Special characters in search", () => {
    const specialPatterns = [
      ".*",
      "^$",
      "\\d+",
      "[a-z]+",
      "(.*)(.*)",
      "test<script>",
      "${variable}",
      "{{template}}",
      "null",
      "undefined",
      "NaN",
    ];

    it.each(specialPatterns)("should not crash when searching for: %s", async (pattern) => {
      const mockSessions = [
        {
          id: 1,
          vault_id: 1,
          title: "Test Session",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 5,
        },
      ];

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: mockSessions });
      vi.mocked(useChatShellStoreModule.useChatShellStore).mockReturnValue(
        createMockStore({ sessionSearchQuery: pattern })
      );

      expect(() => {
        render(
          <Wrapper>
            <SessionRail />
          </Wrapper>
        );
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 8. EMPTY/NULL SESSION DATA
  // ===========================================================================
  describe("Empty/null session data", () => {
    it("renders session with null title as 'Untitled'", async () => {
      const nullTitleSession = {
        id: 1,
        vault_id: 1,
        title: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [nullTitleSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Untitled")).toBeInTheDocument();
      });
    });

    it("handles session with zero message_count", async () => {
      const zeroCountSession = {
        id: 1,
        vault_id: 1,
        title: "Empty Session",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 0,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [zeroCountSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("0 messages")).toBeInTheDocument();
      });
    });

    it("handles session with undefined message_count", async () => {
      const undefinedCountSession = {
        id: 1,
        vault_id: 1,
        title: "No Count",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: undefined,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [undefinedCountSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.queryByText(/messages/)).not.toBeInTheDocument();
      });
    });

    it("handles empty sessions array", async () => {
      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("No sessions yet")).toBeInTheDocument();
      });
    });
  });

  // ===========================================================================
  // 9. LOCALSTORAGE UNAVAILABLE
  // ===========================================================================
  describe("localStorage unavailable", () => {
    it("does not crash when localStorage throws", async () => {
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new Error("QuotaExceededError");
      });

      const mockSession = {
        id: 1,
        vault_id: 1,
        title: "Test",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [mockSession] });

      expect(() => {
        render(
          <Wrapper>
            <SessionRail />
          </Wrapper>
        );
      }).not.toThrow();
    });

    it("handles malformed JSON in localStorage", async () => {
      vi.spyOn(Storage.prototype, "getItem").mockReturnValue("{invalid");
      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [] });

      expect(() => {
        render(
          <Wrapper>
            <SessionRail />
          </Wrapper>
        );
      }).not.toThrow();
    });
  });

  // ===========================================================================
  // 10. CONCURRENT DELETE + CLICK
  // ===========================================================================
  describe("Concurrent delete + click", () => {
    it("handles clicking another session while delete is in progress", async () => {
      const mockSessions = [
        {
          id: 1,
          vault_id: 1,
          title: "Session 1",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 5,
        },
        {
          id: 2,
          vault_id: 1,
          title: "Session 2",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          message_count: 3,
        },
      ];

      let resolveDelete: () => void;
      const deletePromise = new Promise<void>((resolve) => {
        resolveDelete = resolve;
      });

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: mockSessions });
      vi.mocked(api.deleteChatSession).mockReturnValue(deletePromise);
      vi.mocked(mockIsSessionPinned).mockReturnValue(false);

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Session 1")).toBeInTheDocument();
      });

      // Delete session 1
      const session1 = screen.getByText("Session 1").closest('[role="button"]');
      fireEvent.mouseEnter(session1!);
      fireEvent.click(within(session1!).getByLabelText("Delete session"));
      fireEvent.click(screen.getByRole("button", { name: /delete$/i }));

      // Click session 2 while delete is pending
      const session2 = screen.getByText("Session 2").closest('[role="button"]');
      fireEvent.click(session2!);

      expect(mockSetActiveSessionId).toHaveBeenCalledWith("2");

      // Resolve deletion
      await act(async () => {
        resolveDelete!();
      });

      await waitFor(() => {
        expect(screen.queryByText("Session 1")).not.toBeInTheDocument();
      });
    });
  });

  // ===========================================================================
  // ADDITIONAL ADVERSARIAL CASES
  // ===========================================================================
  describe("Additional edge cases", () => {
    it("handles session with negative ID", async () => {
      const negativeIdSession = {
        id: -1,
        vault_id: 1,
        title: "Negative ID",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [negativeIdSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Negative ID")).toBeInTheDocument();
      });
    });

    it("handles future dates", async () => {
      const futureDate = new Date();
      futureDate.setFullYear(futureDate.getFullYear() + 1);
      const futureSession = {
        id: 1,
        vault_id: 1,
        title: "Future",
        created_at: new Date().toISOString(),
        updated_at: futureDate.toISOString(),
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [futureSession] });

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Future")).toBeInTheDocument();
        expect(screen.getByText("Today")).toBeInTheDocument();
      });
    });

    it("handles invalid date format", async () => {
      const invalidDateSession = {
        id: 1,
        vault_id: 1,
        title: "Invalid Date",
        created_at: new Date().toISOString(),
        updated_at: "not-a-date",
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [invalidDateSession] });

      expect(() => {
        render(
          <Wrapper>
            <SessionRail />
          </Wrapper>
        );
      }).not.toThrow();

      await waitFor(() => {
        const elements = screen.getAllByText("Invalid Date");
        expect(elements.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("handles rename failure with revert", async () => {
      const mockSession = {
        id: 1,
        vault_id: 1,
        title: "Original",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 5,
      };

      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: [mockSession] });
      vi.mocked(api.updateChatSession).mockRejectedValue(new Error("Network error"));

      render(
        <Wrapper>
          <SessionRail />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Original")).toBeInTheDocument();
      });

      const sessionElement = screen.getByRole("button", { name: /chat session/i });
      fireEvent.mouseEnter(sessionElement);
      fireEvent.click(screen.getByLabelText("Rename session"));

      await act(async () => {
        vi.runAllTimersAsync();
      });

      const input = screen.getByLabelText("Edit session title");
      await userEvent.clear(input);
      await userEvent.type(input, "New Title");
      fireEvent.click(screen.getByLabelText("Save title"));

      await act(async () => {
        vi.runAllTimersAsync();
      });

      await waitFor(() => {
        expect(screen.getByText("Original")).toBeInTheDocument();
      });
    });
  });

  // ===========================================================================
  // BUG DISCOVERED: Malformed API response
  // ===========================================================================
  describe("Malformed API response handling (BUG DISCOVERY)", () => {
    it("BUG: Should handle API returning {sessions: undefined} instead of array", async () => {
      // This test documents a real bug: groupSessionsByTime crashes when sessions is undefined.
      vi.mocked(api.listChatSessions).mockResolvedValue({ sessions: undefined as any });

      expect(() => {
        render(
          <Wrapper>
            <SessionRail />
          </Wrapper>
        );
      }).not.toThrow();

      // Should show empty state
      await waitFor(() => {
        expect(screen.getByText("No sessions yet")).toBeInTheDocument();
      });
    });
  });
});
