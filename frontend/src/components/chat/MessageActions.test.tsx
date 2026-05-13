import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UserMessageActions } from "./MessageActions";

vi.mock("@/lib/api", () => ({
  updateMessageFeedback: vi.fn(),
}));

describe("UserMessageActions", () => {
  it("disables edit while generation is streaming", async () => {
    const onEdit = vi.fn();
    render(
      <UserMessageActions
        content="question"
        onEdit={onEdit}
        isEditDisabled
      />
    );

    const edit = screen.getByRole("button", { name: "Edit message" });
    expect(edit).toBeDisabled();

    await userEvent.click(edit);
    expect(onEdit).not.toHaveBeenCalled();
  });
});
