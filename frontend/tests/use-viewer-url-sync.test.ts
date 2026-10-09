// The store<->URL sync hook (D-2, DECISIONS.md #28/#29, issue #32): rapid
// sequential agent-driven pushes must not drop one, back/forward and a shared
// URL must restore the exact view, and the list's filter parameters must
// survive every push the reader makes.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

const { pushMock, mockState } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  mockState: { search: "" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => "/demo",
  useSearchParams: () => new URLSearchParams(mockState.search),
}));

import { useViewerUrlSync } from "@/hooks/use-viewer-url-sync";
import { useViewerStore } from "@/stores/viewer-store";

// router.push is async in real Next.js: `searchParams` does not reflect a
// push until the navigation commits (DECISIONS.md 2026-07-09). The mock
// defers the commit until `commitPendingPush()`, so a test can reproduce the
// lag deliberately.
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
  it("pushes a second store-driven change even though the first has not committed", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());

    act(() => useViewerStore.getState().setPaper("1409.7842"));
    rerender();
    expect(pushMock).toHaveBeenNthCalledWith(1, "/demo?paper=1409.7842", { scroll: false });
    expect(mockState.search).toBe(""); // still uncommitted, the lag this targets

    act(() => useViewerStore.getState().setPaper("1409.7842", 3));
    rerender();
    expect(pushMock).toHaveBeenNthCalledWith(2, "/demo?paper=1409.7842&page=3", {
      scroll: false,
    });

    commitPendingPush();
    rerender();
    expect(pushMock).toHaveBeenCalledTimes(2); // settling adds no third push
  });

  it("goto_page's paper+page land in ONE push (D-3.1, via applyDriveAction)", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());

    act(() =>
      useViewerStore
        .getState()
        .applyDriveAction("goto_page", { action: "goto_page", paper_id: "1409.7842", page: 3 }),
    );
    rerender();

    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/demo?paper=1409.7842&page=3", { scroll: false });
  });
});

describe("useViewerUrlSync — the list's filter survives the reader", () => {
  it("opening a paper keeps the filter in the URL", () => {
    mockState.search = "category=cs.CL&sort=cited";
    const { rerender } = renderHook(() => useViewerUrlSync());

    act(() => useViewerStore.getState().setPaper("1409.7842"));
    rerender();

    expect(pushMock).toHaveBeenCalledWith("/demo?category=cs.CL&sort=cited&paper=1409.7842", {
      scroll: false,
    });
  });

  it("closing the paper returns to the same filtered list", () => {
    mockState.search = "category=cs.CL&paper=1409.7842&page=2";
    const { rerender } = renderHook(() => useViewerUrlSync());
    expect(useViewerStore.getState()).toMatchObject({ paper: "1409.7842", page: 2 });

    act(() => useViewerStore.getState().setPaper(null));
    rerender();

    expect(pushMock).toHaveBeenCalledWith("/demo?category=cs.CL", { scroll: false });
  });

  it("a filter change alone is not a viewer change, so it triggers no push", () => {
    const { rerender } = renderHook(() => useViewerUrlSync());
    mockState.search = "category=cs.CL";
    rerender();
    expect(pushMock).not.toHaveBeenCalled();
    expect(useViewerStore.getState()).toMatchObject({ paper: null, page: null });
  });
});

describe("useViewerUrlSync — back/forward + shared URL (issue #32 acceptance item 2)", () => {
  it("a shared URL restores the open paper and page on mount", () => {
    mockState.search = "category=cs.CL&paper=1409.7842&page=3";
    renderHook(() => useViewerUrlSync());
    expect(useViewerStore.getState()).toMatchObject({ paper: "1409.7842", page: 3 });
  });

  it("back and forward re-apply the URL the store did not itself change", () => {
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
