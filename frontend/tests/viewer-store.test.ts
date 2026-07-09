// D-2 (decisions.md): the URL is the source of truth; the store derives
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

const DEFAULT_STATE: ViewerUrlState = {
  q: "",
  category: null,
  yearFrom: null,
  yearTo: null,
  sort: null,
  paper: null,
  page: null,
};

describe("viewerStateFromSearchParams — URL -> state", () => {
  it("parses an empty query string into the default state", () => {
    expect(viewerStateFromSearchParams(new URLSearchParams(""))).toEqual(DEFAULT_STATE);
  });

  it("parses every recognized param", () => {
    const params = new URLSearchParams(
      "q=diffusion+models&category=cs.CL&year_from=2018&year_to=2024&sort=year_asc&paper=2401.00001&page=3",
    );
    expect(viewerStateFromSearchParams(params)).toEqual({
      q: "diffusion models",
      category: "cs.CL",
      yearFrom: 2018,
      yearTo: 2024,
      sort: "year_asc",
      paper: "2401.00001",
      page: 3,
    });
  });

  it("falls back to defaults for malformed year/page and unknown sort", () => {
    const params = new URLSearchParams("year_from=not-a-number&sort=bogus&page=nope");
    const state = viewerStateFromSearchParams(params);
    expect(state.yearFrom).toBeNull();
    expect(state.sort).toBeNull();
    expect(state.page).toBeNull();
  });
});

describe("searchParamsFromViewerState — state -> URL", () => {
  it("omits every default/empty field rather than writing it explicitly", () => {
    expect(searchParamsFromViewerState(DEFAULT_STATE).toString()).toBe("");
  });

  it("writes every non-default field", () => {
    const state: ViewerUrlState = {
      q: "diffusion models",
      category: "cs.CL",
      yearFrom: 2018,
      yearTo: 2024,
      sort: "year_asc",
      paper: "2401.00001",
      page: 3,
    };
    const params = searchParamsFromViewerState(state);
    expect(params.get("q")).toBe("diffusion models");
    expect(params.get("category")).toBe("cs.CL");
    expect(params.get("year_from")).toBe("2018");
    expect(params.get("year_to")).toBe("2024");
    expect(params.get("sort")).toBe("year_asc");
    expect(params.get("paper")).toBe("2401.00001");
    expect(params.get("page")).toBe("3");
  });
});

describe("store <-> URL round trip symmetry", () => {
  const CASES: ViewerUrlState[] = [
    DEFAULT_STATE,
    { ...DEFAULT_STATE, q: "retrieval augmented generation" },
    { ...DEFAULT_STATE, category: "cs.LG", yearFrom: 2020, yearTo: 2026 },
    { ...DEFAULT_STATE, sort: "title_asc" },
    { ...DEFAULT_STATE, paper: "1706.03762", page: 4 },
    {
      q: "attention",
      category: "cs.CL",
      yearFrom: 2017,
      yearTo: 2018,
      sort: "relevance",
      paper: "1706.03762",
      page: 1,
    },
  ];

  it.each(CASES)("state -> URL -> state reproduces the original state (%#)", (state) => {
    const params = searchParamsFromViewerState(state);
    expect(viewerStateFromSearchParams(params)).toEqual(state);
  });

  it.each([
    "",
    "q=hello",
    "category=cs.CV&year_from=2019",
    "sort=year_desc&paper=2606.00001&page=2",
  ])("URL -> state -> URL reproduces the original query string (%s)", (search) => {
    const state = viewerStateFromSearchParams(new URLSearchParams(search));
    expect(searchParamsFromViewerState(state).toString()).toBe(search);
  });
});

describe("useViewerStore actions", () => {
  it("setFilters merges a partial filter change without touching paper/page", () => {
    const { setPaper, setFilters } = useViewerStore.getState();
    setPaper("1706.03762", 4);
    setFilters({ category: "cs.CL" });

    const state = useViewerStore.getState();
    expect(state.category).toBe("cs.CL");
    expect(state.paper).toBe("1706.03762");
    expect(state.page).toBe(4);
  });

  it("setPaper clears page by default (a freshly opened paper has no page anchor)", () => {
    const { setPage, setPaper } = useViewerStore.getState();
    setPage(7);
    setPaper("2401.00001");
    expect(useViewerStore.getState().page).toBeNull();
  });

  it("setPaper accepts an explicit page (drive_ui's goto_page target, once #29 lands)", () => {
    useViewerStore.getState().setPaper("2401.00001", 5);
    expect(useViewerStore.getState().page).toBe(5);
  });

  it("setPage sets the page directly, independent of setPaper", () => {
    useViewerStore.getState().setPaper("2401.00001");
    useViewerStore.getState().setPage(9);
    expect(useViewerStore.getState().page).toBe(9);
    expect(useViewerStore.getState().paper).toBe("2401.00001");
  });

  it("hydrateFromUrl replaces the whole state from a URL, including clearing stale fields", () => {
    const { setFilters, setPaper, hydrateFromUrl } = useViewerStore.getState();
    setFilters({ q: "old query", category: "cs.LG" });
    setPaper("9999.99999", 2);

    hydrateFromUrl(new URLSearchParams("q=new+query"));

    expect(useViewerStore.getState()).toMatchObject({
      q: "new query",
      category: null,
      yearFrom: null,
      yearTo: null,
      sort: null,
      paper: null,
      page: null,
    });
  });

  it("reset returns to the default state", () => {
    useViewerStore.getState().setFilters({ q: "x", category: "cs.CL" });
    useViewerStore.getState().reset();
    expect(useViewerStore.getState()).toMatchObject(DEFAULT_STATE);
  });
});

describe("applyDriveAction — CONFIRMED drive_ui actions only (D-1/D-3, issue #32)", () => {
  it("open_paper sets paper and clears page", () => {
    useViewerStore.getState().setPage(9);
    useViewerStore
      .getState()
      .applyDriveAction("open_paper", { action: "open_paper", paper_id: "1409.7842" });

    const state = useViewerStore.getState();
    expect(state.paper).toBe("1409.7842");
    expect(state.page).toBeNull();
  });

  it("goto_page sets paper+page in ONE update (D-3.1)", () => {
    useViewerStore
      .getState()
      .applyDriveAction("goto_page", { action: "goto_page", paper_id: "1409.7842", page: 3 });

    const state = useViewerStore.getState();
    expect(state.paper).toBe("1409.7842");
    expect(state.page).toBe(3);
  });

  it("set_filters maps year_min/year_max onto yearFrom/yearTo and swaps back to the explorer", () => {
    useViewerStore.getState().setPaper("1409.7842", 2);
    useViewerStore.getState().applyDriveAction("set_filters", {
      action: "set_filters",
      category: "cs.CL",
      year_min: 2018,
      year_max: 2020,
    });

    const state = useViewerStore.getState();
    expect(state.category).toBe("cs.CL");
    expect(state.yearFrom).toBe(2018);
    expect(state.yearTo).toBe(2020);
    // AppRegion keys the explorer<->viewer swap on `paper` (app/page.tsx).
    expect(state.paper).toBeNull();
    expect(state.page).toBeNull();
  });

  it("set_filters only touches the keys the model actually sent — an omitted key is 'no change'", () => {
    useViewerStore.getState().setFilters({ category: "cs.LG", yearFrom: 2015, yearTo: 2019 });
    useViewerStore
      .getState()
      .applyDriveAction("set_filters", { action: "set_filters", category: "cs.CL" });

    const state = useViewerStore.getState();
    expect(state.category).toBe("cs.CL");
    expect(state.yearFrom).toBe(2015); // untouched — the model never sent year_min
    expect(state.yearTo).toBe(2019); // untouched — the model never sent year_max
  });

  it("set_filters with an explicit null category clears it (distinct from an omitted key)", () => {
    useViewerStore.getState().setFilters({ category: "cs.LG" });
    useViewerStore
      .getState()
      .applyDriveAction("set_filters", { action: "set_filters", category: null });

    expect(useViewerStore.getState().category).toBeNull();
  });

  it("goto_page with a missing/malformed target no-ops rather than crashing (forward-compat)", () => {
    useViewerStore.getState().applyDriveAction("goto_page", { action: "goto_page" });
    expect(useViewerStore.getState().paper).toBeNull();
  });

  it("an unrecognized action name no-ops rather than crashing (forward-compat)", () => {
    useViewerStore.getState().setFilters({ category: "cs.CL" });
    useViewerStore.getState().applyDriveAction("some_future_action", {});
    expect(useViewerStore.getState().category).toBe("cs.CL");
  });
});
