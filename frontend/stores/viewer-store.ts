// Explorer/viewer UI state (spec §4c): open paper, page, filters —
// drive_ui's target once #29 lands. D-2 (decisions.md): the URL is the
// SOURCE OF TRUTH; this store derives from it. The store itself never
// touches the URL directly — zustand actions here only set state. The
// actual URL read/write glue is hooks/use-viewer-url-sync.ts, since
// next/navigation's router hooks only run inside a component; this file
// stays framework-router-free so `viewerStateFromSearchParams` /
// `searchParamsFromViewerState` are plain, directly testable functions
// (tests/viewer-store.test.ts — the store⇄URL symmetry acceptance gate).
import { create } from "zustand";

export type SortOption = "relevance" | "year_desc" | "year_asc" | "title_asc";

const SORT_OPTIONS: ReadonlySet<string> = new Set([
  "relevance",
  "year_desc",
  "year_asc",
  "title_asc",
]);

export interface ViewerUrlState {
  q: string;
  category: string | null;
  yearFrom: number | null;
  yearTo: number | null;
  // null = no explicit sort in the URL; routes_explorer.py's `_resolve_sort`
  // picks "relevance" (q set) or "year_desc" (q empty) server-side. The
  // frontend never sends "relevance" itself unless a user action implies
  // search ordering, since sort=relevance with no q is a 400.
  sort: SortOption | null;
  paper: string | null;
  page: number | null;
}

const DEFAULT_STATE: ViewerUrlState = {
  q: "",
  category: null,
  yearFrom: null,
  yearTo: null,
  sort: null,
  paper: null,
  page: null,
};

function parseIntParam(raw: string | null): number | null {
  if (raw === null) return null;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

function parseSort(raw: string | null): SortOption | null {
  return raw !== null && SORT_OPTIONS.has(raw) ? (raw as SortOption) : null;
}

/** URL -> state half of D-2's symmetry. Unknown/malformed params fall back
 * to defaults rather than throwing: a hand-edited or stale URL degrades to
 * the default view instead of crashing the app. */
export function viewerStateFromSearchParams(params: URLSearchParams): ViewerUrlState {
  return {
    q: params.get("q") ?? "",
    category: params.get("category"),
    yearFrom: parseIntParam(params.get("year_from")),
    yearTo: parseIntParam(params.get("year_to")),
    sort: parseSort(params.get("sort")),
    paper: params.get("paper"),
    page: parseIntParam(params.get("page")),
  };
}

/** state -> URL half of D-2's symmetry, the exact inverse of
 * `viewerStateFromSearchParams` for every field it recognizes. Default/empty
 * values are OMITTED (never written as `q=` or `category=null`) so the URL
 * stays clean at the default view — this is what makes the round trip
 * exact rather than merely lossless. */
export function searchParamsFromViewerState(state: ViewerUrlState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.category) params.set("category", state.category);
  if (state.yearFrom !== null) params.set("year_from", String(state.yearFrom));
  if (state.yearTo !== null) params.set("year_to", String(state.yearTo));
  if (state.sort) params.set("sort", state.sort);
  if (state.paper) params.set("paper", state.paper);
  if (state.page !== null) params.set("page", String(state.page));
  return params;
}

export interface ViewerStoreState extends ViewerUrlState {
  setFilters: (partial: Partial<Omit<ViewerUrlState, "paper" | "page">>) => void;
  // Row click (the #29 seam): sets the open paper and, unless given, clears
  // the page — a freshly opened paper has no page anchor yet.
  setPaper: (paper: string | null, page?: number | null) => void;
  setPage: (page: number | null) => void;
  // The ONLY setter that writes state from outside a UI intent — called by
  // use-viewer-url-sync.ts when the browser URL changes (nav, back/forward,
  // a pasted link), never by a component reacting to user input.
  hydrateFromUrl: (params: URLSearchParams) => void;
  reset: () => void;
}

export const useViewerStore = create<ViewerStoreState>()((set) => ({
  ...DEFAULT_STATE,

  setFilters: (partial) => set(partial),

  setPaper: (paper, page = null) => set({ paper, page }),

  setPage: (page) => set({ page }),

  hydrateFromUrl: (params) => set(viewerStateFromSearchParams(params)),

  reset: () => set(DEFAULT_STATE),
}));
