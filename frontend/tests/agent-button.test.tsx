// The agent is on demand at every width, and this button is the only way in.
// Its contract: it toggles the panel that exists at the current width (a
// column from `lg:` up, a sheet below), reports that through aria-expanded,
// and shows a running turn while the panel is shut.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AgentButton } from "@/components/shell/agent-button";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";

function installMatchMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    media: query,
    matches,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

beforeEach(() => {
  useAgentSessionStore.getState().reset();
  useUiShellStore.setState({ overlay: "none", agentColumn: false });
  installMatchMedia(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AgentButton", () => {
  it("toggles the agent sheet open and shut below lg", () => {
    render(<AgentButton />);
    const button = screen.getByRole("button", { name: /agent/i });

    fireEvent.click(button);
    expect(useUiShellStore.getState().overlay).toBe("agent");
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(button);
    expect(useUiShellStore.getState().overlay).toBe("none");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("toggles the docked column from lg up, leaving the sheet state alone", () => {
    installMatchMedia(true);
    render(<AgentButton />);
    const button = screen.getByRole("button", { name: /agent/i });
    expect(button).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(button);
    expect(useUiShellStore.getState().agentColumn).toBe(true);
    expect(useUiShellStore.getState().overlay).toBe("none");
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(button);
    expect(useUiShellStore.getState().agentColumn).toBe(false);
  });

  it("marks itself busy while a turn is running", () => {
    useAgentSessionStore.setState({ status: { kind: "tool_running", name: "search_corpus" } });
    const { container } = render(<AgentButton />);
    // The dot is decorative (aria-hidden); what matters is that it appears.
    expect(container.querySelector(".bg-amber")).toBeInTheDocument();
  });

  it("shows no busy dot when nothing is running", () => {
    const { container } = render(<AgentButton />);
    expect(container.querySelector(".bg-amber")).not.toBeInTheDocument();
  });

  it("shows at every width, with a hover treatment", () => {
    render(<AgentButton />);
    const button = screen.getByRole("button", { name: /agent/i });
    expect(button.className).toMatch(/hover:/);
    expect(button.className).not.toMatch(/lg:hidden/);
  });
});
