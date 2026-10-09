// One control, two panels: from `lg:` up the agent is a docked column with
// its own flag, below it a sheet on the shell overlay. The hook must route
// each call to the panel that exists, so closing the column never touches
// the overlay (use-drive-ui.ts closes that after every agent action).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useAgentPanel } from "@/hooks/use-agent-panel";
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
  useUiShellStore.setState({ overlay: "none", agentColumn: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useAgentPanel", () => {
  it("starts closed at both widths", () => {
    installMatchMedia(true);
    expect(renderHook(() => useAgentPanel()).result.current.open).toBe(false);
    installMatchMedia(false);
    expect(renderHook(() => useAgentPanel()).result.current.open).toBe(false);
  });

  it("drives the column when docked", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useAgentPanel());
    act(() => result.current.toggle());
    expect(result.current.open).toBe(true);
    expect(useUiShellStore.getState().overlay).toBe("none");
    act(() => result.current.close());
    expect(useUiShellStore.getState().agentColumn).toBe(false);
  });

  it("keeps the column open when the sheet state is cleared", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useAgentPanel());
    act(() => result.current.toggle());
    act(() => useUiShellStore.getState().closeOverlay());
    expect(result.current.open).toBe(true);
  });

  it("drives the sheet below lg", () => {
    installMatchMedia(false);
    const { result } = renderHook(() => useAgentPanel());
    act(() => result.current.toggle());
    expect(useUiShellStore.getState().overlay).toBe("agent");
    expect(useUiShellStore.getState().agentColumn).toBe(false);
    act(() => result.current.close());
    expect(result.current.open).toBe(false);
  });
});
