// Below `lg:` the agent panel is a closed sheet, and this button is the only
// way back to it. Its contract: it toggles the sheet, reports that through
// aria-expanded, and shows a running turn while the sheet is shut.
import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AgentButton } from "@/components/shell/agent-button";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";

beforeEach(() => {
  useAgentSessionStore.getState().reset();
  useUiShellStore.setState({ overlay: "none" });
});

describe("AgentButton", () => {
  it("toggles the agent sheet open and shut", () => {
    render(<AgentButton />);
    const button = screen.getByRole("button", { name: /agent/i });

    fireEvent.click(button);
    expect(useUiShellStore.getState().overlay).toBe("agent");
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(button);
    expect(useUiShellStore.getState().overlay).toBe("none");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("marks itself busy while a turn is running", () => {
    useAgentSessionStore.setState({ status: { kind: "tool_running", name: "search_corpus" } });
    const { container } = render(<AgentButton />);
    // The dot is decorative (aria-hidden); what matters is that it changes.
    expect(container.querySelector(".bg-amber")).toBeInTheDocument();
    expect(container.querySelector(".bg-teal")).not.toBeInTheDocument();
  });

  it("shows the idle dot when nothing is running", () => {
    const { container } = render(<AgentButton />);
    expect(container.querySelector(".bg-teal")).toBeInTheDocument();
    expect(container.querySelector(".bg-amber")).not.toBeInTheDocument();
  });

  it("has a hover treatment and hides where the panel is docked", () => {
    render(<AgentButton />);
    const button = screen.getByRole("button", { name: /agent/i });
    expect(button.className).toMatch(/hover:/);
    expect(button.className).toMatch(/lg:hidden/);
  });
});
