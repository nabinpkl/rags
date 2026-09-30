// The shell's overlay state is a three-value machine, not two booleans: the
// filters drawer and the agent sheet are both full-height overlays on the
// same narrow screen, so "both open" must be unrepresentable rather than
// merely unreachable.
import { beforeEach, describe, expect, it } from "vitest";
import { useUiShellStore } from "@/stores/ui-shell-store";

beforeEach(() => {
  useUiShellStore.setState({ overlay: "none", agentColumn: false });
});

describe("useUiShellStore", () => {
  it("starts with nothing open", () => {
    expect(useUiShellStore.getState().overlay).toBe("none");
  });

  it("keeps the docked agent column closed until asked, apart from the overlay", () => {
    expect(useUiShellStore.getState().agentColumn).toBe(false);
    useUiShellStore.getState().setAgentColumn(true);
    useUiShellStore.getState().closeOverlay();
    expect(useUiShellStore.getState().agentColumn).toBe(true);
  });

  it("opens the filters drawer", () => {
    useUiShellStore.getState().openFilters();
    expect(useUiShellStore.getState().overlay).toBe("filters");
  });

  it("opens the agent sheet", () => {
    useUiShellStore.getState().openAgent();
    expect(useUiShellStore.getState().overlay).toBe("agent");
  });

  it("replaces one overlay with the other instead of stacking them", () => {
    useUiShellStore.getState().openFilters();
    useUiShellStore.getState().openAgent();
    expect(useUiShellStore.getState().overlay).toBe("agent");

    useUiShellStore.getState().openFilters();
    expect(useUiShellStore.getState().overlay).toBe("filters");
  });

  it("toggles the agent sheet shut only when the agent is what's open", () => {
    useUiShellStore.getState().toggleAgent();
    expect(useUiShellStore.getState().overlay).toBe("agent");

    useUiShellStore.getState().toggleAgent();
    expect(useUiShellStore.getState().overlay).toBe("none");

    // From the filters drawer, the agent button opens the agent — it does not
    // toggle the unrelated drawer closed and leave nothing open.
    useUiShellStore.getState().openFilters();
    useUiShellStore.getState().toggleAgent();
    expect(useUiShellStore.getState().overlay).toBe("agent");
  });

  it("closes whatever is open", () => {
    useUiShellStore.getState().openAgent();
    useUiShellStore.getState().closeOverlay();
    expect(useUiShellStore.getState().overlay).toBe("none");
  });
});
