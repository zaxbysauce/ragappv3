import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { MobileBottomNav } from "./MobileBottomNav";

const mockLogout = vi.hoisted(() => vi.fn());

vi.mock("@/stores/useAuthStore", () => ({
  useAuthStore: vi.fn((selector: (s: { user: { role: string } | null; logout: () => Promise<void> }) => unknown) =>
    selector({ user: { role: "admin" }, logout: mockLogout })
  ),
}));

describe("MobileBottomNav", () => {
  beforeEach(() => {
    mockLogout.mockResolvedValue(undefined);
    mockLogout.mockClear();
  });

  it("exposes logout in the more sheet", async () => {
    render(
      <MemoryRouter>
        <MobileBottomNav activeItem="chat" onItemSelect={vi.fn()} />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByLabelText("More navigation options"));
    fireEvent.click(screen.getByLabelText("Log out"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
  });
});
