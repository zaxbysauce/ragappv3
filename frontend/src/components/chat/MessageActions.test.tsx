import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { updateMessageFeedback } from "@/lib/api";
import { AssistantMessageActions } from "./MessageActions";

vi.mock("@/lib/api", () => ({
  updateMessageFeedback: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
  },
}));

describe("AssistantMessageActions feedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(localStorage.getItem).mockReturnValue(null);
    vi.mocked(updateMessageFeedback).mockResolvedValue({} as Awaited<ReturnType<typeof updateMessageFeedback>>);
  });

  it("sends the selected feedback rating to the API", () => {
    render(<AssistantMessageActions content="Answer" sessionId="7" messageId="42" />);

    fireEvent.click(screen.getByLabelText("Good response"));

    expect(updateMessageFeedback).toHaveBeenCalledWith(7, 42, "up");
  });

  it("cycles feedback between up, down, and cleared", () => {
    render(<AssistantMessageActions content="Answer" sessionId="7" messageId="42" />);

    const good = screen.getByLabelText("Good response");
    const bad = screen.getByLabelText("Bad response");

    fireEvent.click(good);
    expect(good).toHaveAttribute("aria-pressed", "true");
    expect(updateMessageFeedback).toHaveBeenLastCalledWith(7, 42, "up");

    fireEvent.click(bad);
    expect(bad).toHaveAttribute("aria-pressed", "true");
    expect(updateMessageFeedback).toHaveBeenLastCalledWith(7, 42, "down");

    fireEvent.click(bad);
    expect(bad).toHaveAttribute("aria-pressed", "false");
    expect(updateMessageFeedback).toHaveBeenLastCalledWith(7, 42, null);
  });

  it("rolls back to resolved external feedback when save fails", async () => {
    vi.mocked(updateMessageFeedback).mockRejectedValueOnce(new Error("offline"));
    const onFeedback = vi.fn();

    render(
      <AssistantMessageActions
        content="Answer"
        sessionId="7"
        messageId="42"
        externalFeedback="up"
        onFeedback={onFeedback}
      />
    );

    fireEvent.click(screen.getByLabelText("Bad response"));

    expect(onFeedback).toHaveBeenCalledWith("down");
    await waitFor(() => expect(onFeedback).toHaveBeenLastCalledWith("up"));
    expect(localStorage.setItem).toHaveBeenLastCalledWith("chat_feedback_42", "up");
    expect(toast.error).toHaveBeenCalledWith("Couldn't save feedback");
  });

  it("uses localStorage only when the server has no feedback value", () => {
    vi.mocked(localStorage.getItem).mockReturnValue("up");

    const { rerender } = render(
      <AssistantMessageActions content="Answer" sessionId="7" messageId="42" />
    );

    expect(screen.getByLabelText("Good response")).toHaveAttribute("aria-pressed", "true");

    rerender(
      <AssistantMessageActions content="Answer" sessionId="7" messageId="42" serverFeedback={null} />
    );

    expect(screen.getByLabelText("Good response")).toHaveAttribute("aria-pressed", "false");
    expect(localStorage.removeItem).toHaveBeenCalledWith("chat_feedback_42");
  });
});
