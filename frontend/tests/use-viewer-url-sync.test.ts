// The store<->URL sync hook (D-2, DECISIONS.md #28/#29). This file is new
// (issue #32): D-3 requires proving this hook survives RAPID SEQUENTIAL
// agent-driven pushes (open->page->filter landing across ticks) without
// dropping one, and that back/forward + a shared URL restore the exact
// view — acceptance item 2.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

const { pushMock, mockState } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  mockState: { search: "" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(mockState.search),
}));

import { useViewerUrlSync } from "@/hooks/use-viewer-url-sync";
import { useViewerStore } from "@/stores/viewer-store";

// router.push is async in real Next.js — `searchParams` doesn't reflect a
// push until the navigation commits, often several ticks later (round-1
// review finding, DECISIONS.md 2026-07-09). The mock defers committing to
// `mockState.search` until `commitPendingPush()` runs, so a test can
// reproduce that lag deliberately instead of the push landing synchronously.
let pendingSearch: string | null = null;

function commitPendingPush() {
  if (pendingSearch !== null) {
    mockState.search = pendingSearch;
    pendingSearch = null;
  }
}

beforeEach(() => {
  useViewerStore.getState().reset();
  pushMock.mockReset();
  pushMock.mockImplementation((url: string) => {
    pendingSearch = url.includes("?") ? url.slice(url.indexOf("?") + 1) : "";
  });
  mockState.search = "";
  pendingSearch = null;
});

describe("useViewerUrlSync — sequential agent-driven pushes (D-3, issue #32)", () => {
  it("pushes a second store-driven change even though the first push hasn't committed to the URL yet", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());

    act(() => {
      useViewerStore.getState().setPaper("1409.7842");
    });
    rerender();
    expect(pushMock).toHaveBeenNthCalledWith(1, "/?paper=1409.7842", { scroll: false });
    expect(mockState.search).toBe(""); // still uncommitted — the lag this test targets

    act(() => {
      useViewerStore.getState().setPaper("1409.7842", 3); // goto_page-shaped: paper+page together
    });
    rerender();
    expect(pushMock).toHaveBeenNthCalledWith(2, "/?paper=1409.7842&page=3", { scroll: false });

    commitPendingPush();
    rerender();
    // Settling the now-committed URL matches the store exactly — no
    // spurious third push.
    expect(pushMock).toHaveBeenCalledTimes(2);
  });

  it("goto_page's paper+page land in ONE push, not two (D-3.1, via applyDriveAction)", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());

    act(() => {
      useViewerStore.getState().applyDriveAction("goto_page", {
        action: "goto_page",
        paper_id: "1409.7842",
        page: 3,
      });
    });
    rerender();

    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/?paper=1409.7842&page=3", { scroll: false });
  });

  it("a three-step agent sequence (open -> page jump -> filters back to explorer) never drops a step", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());

    act(() => {
      useViewerStore.getState().applyDriveAction("open_paper", {
        action: "open_paper",
        paper_id: "1409.7842",
      });
    });
    rerender();
    expect(mockState.search).toBe(""); // uncommitted

    act(() => {
      useViewerStore.getState().applyDriveAction("goto_page", {
        action: "goto_page",
        paper_id: "1409.7842",
        page: 3,
      });
    });
    rerender();
    expect(mockState.search).toBe(""); // still uncommitted — second push landed anyway

    act(() => {
      useViewerStore
        .getState()
        .applyDriveAction("set_filters", { action: "set_filters", category: "cs.CL" });
    });
    rerender();

    expect(pushMock).toHaveBeenCalledTimes(3);
    expect(pushMock).toHaveBeenLastCalledWith("/?category=cs.CL", { scroll: false });

    commitPendingPush();
    rerender();
    expect(pushMock).toHaveBeenCalledTimes(3); // settling doesn't add a fourth push
    expect(useViewerStore.getState()).toMatchObject({ category: "cs.CL", paper: null, page: null });
  });
});

describe("useViewerUrlSync — back/forward + shared URL (issue #32 acceptance item 2)", () => {
  it("a shared URL (paper+page+filters together) restores the exact view on mount", () => {
    mockState.search = "category=cs.CL&year_from=2018&paper=1409.7842&page=3";
    renderHook(() => useViewerUrlSync());

    expect(useViewerStore.getState()).toMatchObject({
      category: "cs.CL",
      yearFrom: 2018,
      paper: "1409.7842",
      page: 3,
    });
  });

  it("back button (URL reverts externally, store didn't change) hydrates the store back to match", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());

    act(() => {
      useViewerStore.getState().setFilters({ category: "cs.CL" });
    });
    rerender();
    commitPendingPush();
    rerender(); // settle: the hook's prevStoreString now reflects the pushed state

    // Simulate the browser back button: the URL reverts externally, the
    // store has not itself changed.
    mockState.search = "";
    rerender();

    expect(useViewerStore.getState().category).toBeNull();
  });

  it("forward button re-applies a later agent-driven URL the same way", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());

    mockState.search = "paper=1409.7842&page=5";
    rerender();
    expect(useViewerStore.getState()).toMatchObject({ paper: "1409.7842", page: 5 });

    mockState.search = ""; // back
    rerender();
    expect(useViewerStore.getState().paper).toBeNull();

    mockState.search = "paper=1409.7842&page=5"; // forward
    rerender();
    expect(useViewerStore.getState()).toMatchObject({ paper: "1409.7842", page: 5 });
  });
});
