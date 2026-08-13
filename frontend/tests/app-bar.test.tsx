// The narrow-viewport bar is the ONLY way back to the two panels that undock
// below `lg:`. Its contract: the agent is always reachable, the filters
// button appears only where filters mean something, and a running turn is
// visible while the sheet is closed.
import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AppBar } from "@/components/shell/app-bar";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";

beforeEach(() => {
  useViewerStore.getState().reset();
  useAgentSessionStore.getState().reset();
  useUiShellStore.setState({ overlay: "none" });
});

describe("AppBar", () => {
  it("opens the filters drawer from the hamburger", () => {
    render(<AppBar />);
    fireEvent.click(screen.getByRole("button", { name: /open filters/i }));
    expect(useUiShellStore.getState().overlay).toBe("filters");
  });

  it("hides the filters button in the viewer, where there is nothing to filter", () => {
    useViewerStore.getState().setPaper("2602.02985");
    render(<AppBar />);
    expect(screen.queryByRole("button", { name: /open filters/i })).not.toBeInTheDocument();
    // The agent, by contrast, stays reachable while reading a paper.
    expect(screen.getByRole("button", { name: /agent/i })).toBeInTheDocument();
  });

  it("toggles the agent sheet open and shut", () => {
    render(<AppBar />);
    const button = screen.getByRole("button", { name: /agent/i });

    fireEvent.click(button);
    expect(useUiShellStore.getState().overlay).toBe("agent");
    expect(button).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(button);
    expect(useUiShellStore.getState().overlay).toBe("none");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("reports the drawer state through aria-expanded", () => {
    render(<AppBar />);
    const filters = screen.getByRole("button", { name: /open filters/i });
    expect(filters).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(filters);
    expect(filters).toHaveAttribute("aria-expanded", "true");
  });

  it("marks the agent button busy while a turn is running", () => {
    useAgentSessionStore.setState({ status: { kind: "tool_running", name: "search_corpus" } });
    const { container } = render(<AppBar />);
    // The dot is decorative (aria-hidden); what matters is that it changes,
    // since a closed sheet hides every other sign that the agent is working.
    expect(container.querySelector(".bg-amber")).toBeInTheDocument();
    expect(container.querySelector(".bg-teal")).not.toBeInTheDocument();
  });

  it("shows the idle dot when nothing is running", () => {
    const { container } = render(<AppBar />);
    expect(container.querySelector(".bg-teal")).toBeInTheDocument();
    expect(container.querySelector(".bg-amber")).not.toBeInTheDocument();
  });
});
