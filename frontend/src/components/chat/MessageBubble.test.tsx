import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "@/stores/useChatStore";

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: { children: React.ReactNode }) => (
      <div {...props}>{children}</div>
    ),
  },
  useReducedMotion: () => true,
}));

vi.mock("./MessageActions", () => ({
  UserMessageActions: () => <div data-testid="message-actions" />,
}));

vi.mock("./MarkdownMessage", () => ({
  MarkdownMessage: ({ content }: { content: string }) => (
    <div data-testid="markdown-message">{content}</div>
  ),
}));

const createMessage = (overrides: Partial<Message> = {}): Message => ({
  id: "msg-1",
  role: "user",
  content: "Hello",
  ...overrides,
});

describe("MessageBubble avatar initials", () => {
  it("renders the supplied user initial in the user avatar", () => {
    render(<MessageBubble message={createMessage()} userInitial="B" />);

    expect(screen.getByLabelText("Your message")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("renders the supplied initial for the assistant fallback branch", () => {
    render(
      <MessageBubble
        message={createMessage({ role: "assistant", content: "Assistant fallback" })}
        userInitial="U"
      />
    );

    expect(screen.getByLabelText("Assistant message")).toBeInTheDocument();
    expect(screen.getByText("U")).toBeInTheDocument();
    expect(screen.getByTestId("markdown-message")).toHaveTextContent("Assistant fallback");
  });
});
