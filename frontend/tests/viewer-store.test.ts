// D-2 (DECISIONS.md): the URL is the source of truth; the store derives
// from it. This is the acceptance gate — store <-> URL symmetry, both pure
// conversion functions and the store's own actions.
import { beforeEach, describe, expect, it } from "vitest";
import {
  searchParamsFromViewerState,
  useViewerStore,
  viewerStateFromSearchParams,
  type ViewerUrlState,
} from "@/stores/viewer-store";

beforeEach(() => {
  useViewerStore.getState().reset();
});

const DEFAULT_STATE: ViewerUrlState = { paper: null, page: null };

describe("viewerStateFromSearchParams — URL -> state", () => {
  it("parses an empty query string into the default state", () => {
    expect(viewerStateFromSearchParams(new URLSearchParams(""))).toEqual(DEFAULT_STATE);
  });

  it("parses paper and page", () => {
    expect(viewerStateFromSearchParams(new URLSearchParams("paper=2401.00001&page=3"))).toEqual({
      paper: "2401.00001",
      page: 3,
    });
  });

  it("ignores the list's filter parameters, which this store does not own", () => {
    const params = new URLSearchParams("q=diffusion&category=cs.CL&sort=cited&paper=2401.00001");
    expect(viewerStateFromSearchParams(params)).toEqual({ paper: "2401.00001", page: null });
  });

  it("falls back to null for a malformed page", () => {
    expect(viewerStateFromSearchParams(new URLSearchParams("page=nope")).page).toBeNull();
  });
});

describe("searchParamsFromViewerState — state -> URL", () => {
  it("omits empty fields rather than writing them explicitly", () => {
    expect(searchParamsFromViewerState(DEFAULT_STATE).toString()).toBe("");
  });

  it("writes paper and page", () => {
    expect(searchParamsFromViewerState({ paper: "2401.00001", page: 3 }).toString()).toBe(
      "paper=2401.00001&page=3",
    );
  });

  it("passes the list's filter through untouched, so closing a paper returns to that list", () => {
    const base = new URLSearchParams("category=cs.CL&sort=cited&paper=2401.00001&page=4");
    expect(searchParamsFromViewerState(DEFAULT_STATE, base).toString()).toBe(
      "category=cs.CL&sort=cited",
    );
    expect(searchParamsFromViewerState({ paper: "2402.00002", page: null }, base).toString()).toBe(
      "category=cs.CL&sort=cited&paper=2402.00002",
    );
  });

  it("round-trips exactly for the keys it owns", () => {
    const state: ViewerUrlState = { paper: "2401.00001", page: 7 };
    expect(viewerStateFromSearchParams(searchParamsFromViewerState(state))).toEqual(state);
  });
});

describe("useViewerStore actions", () => {
  it("setPaper clears the page unless one is given", () => {
    useViewerStore.getState().setPaper("2401.00001", 5);
    useViewerStore.getState().setPaper("2402.00002");
    expect(useViewerStore.getState()).toMatchObject({ paper: "2402.00002", page: null });
  });

  it("setPage moves within the open paper", () => {
    useViewerStore.getState().setPaper("2401.00001");
    useViewerStore.getState().setPage(4);
    expect(useViewerStore.getState()).toMatchObject({ paper: "2401.00001", page: 4 });
  });

  it("hydrateFromUrl replaces state from a URL", () => {
    useViewerStore.getState().hydrateFromUrl(new URLSearchParams("paper=2401.00001&page=2"));
    expect(useViewerStore.getState()).toMatchObject({ paper: "2401.00001", page: 2 });
  });
});

describe("applyDriveAction (D-1/D-3, issue #32)", () => {
  it("open_paper opens the paper at no particular page", () => {
    useViewerStore.getState().setPaper("2401.00001", 9);
    useViewerStore
      .getState()
      .applyDriveAction("open_paper", { action: "open_paper", paper_id: "2402.00002" });
    expect(useViewerStore.getState()).toMatchObject({ paper: "2402.00002", page: null });
  });

  it("goto_page sets paper and page in one update", () => {
    useViewerStore
      .getState()
      .applyDriveAction("goto_page", { action: "goto_page", paper_id: "2401.00001", page: 3 });
    expect(useViewerStore.getState()).toMatchObject({ paper: "2401.00001", page: 3 });
  });

  it("ignores an action with a missing or mistyped target", () => {
    useViewerStore.getState().applyDriveAction("open_paper", { action: "open_paper" });
    useViewerStore
      .getState()
      .applyDriveAction("goto_page", { action: "goto_page", paper_id: "2401.00001", page: "3" });
    expect(useViewerStore.getState()).toMatchObject(DEFAULT_STATE);
  });

  it("leaves set_filters to use-drive-ui.ts, which writes the list's filter to the URL", () => {
    useViewerStore.getState().setPaper("2401.00001");
    useViewerStore
      .getState()
      .applyDriveAction("set_filters", { action: "set_filters", category: "cs.CL" });
    expect(useViewerStore.getState()).toMatchObject({ paper: "2401.00001", page: null });
  });
});
