// The confirmed-agent-action bridge (D-2, DECISIONS.md, issue #32).
// Behavioral tests over a mocked confirmed-ui_action SSE sequence. Reader
// actions land in viewer-store; set_filters lands in the URL, the list
// filter's only home, so the router is mocked to observe it.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

const { replaceMock, mockState } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  mockState: { search: "" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => "/demo",
  useSearchParams: () => new URLSearchParams(mockState.search),
}));

import { useDriveUi } from "@/hooks/use-drive-ui";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";

beforeEach(() => {
  replaceMock.mockReset();
  mockState.search = "";
  useAgentSessionStore.getState().reset();
  useViewerStore.getState().reset();
  useUiShellStore.setState({ overlay: "none" });
});

describe("useDriveUi — the agent sheet gets out of its own way (#83)", () => {
  it("closes the overlay once an action is applied", () => {
    renderHook(() => useDriveUi());
    useUiShellStore.getState().openAgent();
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("open that one");
      applyEvent({
        type: "ui_action",
        action: "open_paper",
        args: { action: "open_paper", paper_id: "1409.7842" },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });
    });

    // The sheet covered the viewer it just opened; on a docked layout there
    // is no overlay and this is simply already "none".
    expect(useViewerStore.getState().paper).toBe("1409.7842");
    expect(useUiShellStore.getState().overlay).toBe("none");
  });

  it("leaves the overlay alone when no action was confirmed", () => {
    renderHook(() => useDriveUi());
    useUiShellStore.getState().openAgent();
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("just chatting");
      applyEvent({ type: "text", text: "no ui action here" });
    });

    expect(useUiShellStore.getState().overlay).toBe("agent");
  });
});

describe("useDriveUi — applies only CONFIRMED ui_actions (D-1, issue #32)", () => {
  it("does not touch viewer-store on the raw/provisional ui_action alone", () => {
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("open that one");
      applyEvent({
        type: "ui_action",
        action: "open_paper",
        args: { action: "open_paper", paper_id: "1409.7842" },
      });
    });

    expect(useViewerStore.getState().paper).toBeNull();
  });

  it("applies open_paper to viewer-store once its paired result is ok=true", () => {
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("open that one");
      applyEvent({
        type: "ui_action",
        action: "open_paper",
        args: { action: "open_paper", paper_id: "1409.7842" },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });
    });

    expect(useViewerStore.getState().paper).toBe("1409.7842");
  });

  it("never applies a rejected (ok=false) ui_action — a hallucinated target never navigates", () => {
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("open a fake one");
      applyEvent({
        type: "ui_action",
        action: "open_paper",
        args: { action: "open_paper", paper_id: "9999.99999" },
      });
      applyEvent({
        type: "tool_result_summary",
        name: "drive_ui",
        ok: false,
        error: "no such paper",
      });
    });

    expect(useViewerStore.getState().paper).toBeNull();
  });

  it("applies goto_page's paper+page together (D-3.1)", () => {
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("jump to page 3");
      applyEvent({
        type: "ui_action",
        action: "goto_page",
        args: { action: "goto_page", paper_id: "1409.7842", page: 3 },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });
    });

    const state = useViewerStore.getState();
    expect(state.paper).toBe("1409.7842");
    expect(state.page).toBe(3);
  });

  it("writes set_filters to the URL and leaves the reader, keeping the rest of the filter", () => {
    mockState.search = "sort=cited&category=cs.CV&paper=1409.7842&page=2";
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("show me the cs.CL papers");
      applyEvent({
        type: "ui_action",
        action: "set_filters",
        args: { action: "set_filters", category: "cs.CL" },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });
    });

    expect(replaceMock).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith("/demo?sort=cited&category=cs.CL", {
      scroll: false,
    });
  });

  it("set_filters with category null clears it; an omitted category is left alone", () => {
    mockState.search = "category=cs.CV";
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("clear it");
      applyEvent({
        type: "ui_action",
        action: "set_filters",
        args: { action: "set_filters", category: null },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });
    });
    expect(replaceMock).toHaveBeenLastCalledWith("/demo", { scroll: false });

    act(() => {
      startTurn("no category at all");
      applyEvent({ type: "ui_action", action: "set_filters", args: { action: "set_filters" } });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });
    });
    expect(replaceMock).toHaveBeenLastCalledWith("/demo?category=cs.CV", { scroll: false });
  });

  it("does not re-apply an already-drained action when an unrelated store field changes later", () => {
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("open that one");
      applyEvent({
        type: "ui_action",
        action: "open_paper",
        args: { action: "open_paper", paper_id: "1409.7842" },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });
    });
    expect(useAgentSessionStore.getState().confirmedUiActions).toHaveLength(0); // drained

    act(() => {
      useViewerStore.getState().setPage(9); // local navigation after the agent's own jump
      applyEvent({ type: "text", text: "some streamed answer text" });
    });

    // The drained open_paper is never re-applied — local navigation sticks.
    expect(useViewerStore.getState().paper).toBe("1409.7842");
    expect(useViewerStore.getState().page).toBe(9);
  });

  it("scripted turn (mock parity): search -> open paper -> page jump -> excerpt highlight, all agent-driven", () => {
    renderHook(() => useDriveUi());
    const { startTurn, applyEvent } = useAgentSessionStore.getState();

    act(() => {
      startTurn("How has cs.CL research grown, and what's a landmark result?");

      // search: an ordinary tool_call, not a ui_action — nothing for
      // useDriveUi to do here.
      applyEvent({
        type: "tool_call",
        name: "search_corpus",
        args: { query: "end-to-end speech recognition" },
      });
      applyEvent({ type: "tool_result_summary", name: "search_corpus", ok: true, error: null });

      // open paper
      applyEvent({
        type: "ui_action",
        action: "open_paper",
        args: { action: "open_paper", paper_id: "1409.7842" },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });

      // page jump
      applyEvent({
        type: "ui_action",
        action: "goto_page",
        args: { action: "goto_page", paper_id: "1409.7842", page: 3 },
      });
      applyEvent({ type: "tool_result_summary", name: "drive_ui", ok: true, error: null });

      // excerpt highlight: citations land for cited-excerpts-pane.tsx (#29)
      // to resolve against.
      applyEvent({
        type: "done",
        stop_reason: "end_turn",
        run_id: "r1",
        citations: [{ paper_id: "1409.7842", chunk_ids: ["c1"] }],
      });
    });

    const viewer = useViewerStore.getState();
    expect(viewer.paper).toBe("1409.7842");
    expect(viewer.page).toBe(3);
    expect(useAgentSessionStore.getState().citationsByPaper.get("1409.7842")).toEqual(["c1"]);
    expect(useAgentSessionStore.getState().confirmedUiActions).toHaveLength(0); // fully drained
  });
});
