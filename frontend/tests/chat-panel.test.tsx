// The empty panel is the first thing a new visitor sees of the agent, and a
// blank composer is a blank page. The starters have one hard rule: they fill
// the composer and never submit — a turn costs money against the D11 caps,
// so spending one must always be the visitor's own keypress.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { useAgentSessionStore } from "@/stores/agent-session-store";

const ask = vi.fn();
vi.mock("@/hooks/use-agent-stream", () => ({
  useAgentStream: () => ({ ask }),
}));

beforeEach(() => {
  useAgentSessionStore.getState().reset();
  ask.mockReset();
});

describe("ChatPanel", () => {
  it("offers example questions on first run", () => {
    render(<ChatPanel />);
    const list = screen.getByRole("list", { name: /example questions/i });
    expect(within(list).getAllByRole("button").length).toBeGreaterThanOrEqual(2);
  });

  it("fills the composer from an example and focuses it, without spending a turn", () => {
    render(<ChatPanel />);
    const [first] = within(screen.getByRole("list", { name: /example questions/i })).getAllByRole(
      "button",
    );
    fireEvent.click(first);

    const input = screen.getByRole("textbox", { name: /question for the agent/i });
    expect(input).toHaveValue(first.textContent);
    expect(input).toHaveFocus();
    expect(ask).not.toHaveBeenCalled();
    // The filled composer is submittable — the Ask button is no longer inert.
    expect(screen.getByRole("button", { name: /^ask$/i })).toBeEnabled();
  });

  it("submits the filled example only on the visitor's own submit", () => {
    render(<ChatPanel />);
    const [first] = within(screen.getByRole("list", { name: /example questions/i })).getAllByRole(
      "button",
    );
    fireEvent.click(first);
    fireEvent.submit(screen.getByRole("textbox", { name: /question for the agent/i }));
    expect(ask).toHaveBeenCalledWith(first.textContent);
  });
});
