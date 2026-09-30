// Viewer UI state (spec §4c): which paper is open, and at which page.
// D-2 (DECISIONS.md): the URL is the SOURCE OF TRUTH; this store derives from
// it. The store itself never touches the URL — zustand actions here only set
// state. The read/write glue is hooks/use-viewer-url-sync.ts, since
// next/navigation's router hooks only run inside a component; this file stays
// router-free so the two pure functions below are directly testable
// (tests/viewer-store.test.ts — the store⇄URL symmetry gate).
//
// Only `paper` and `page`. The list's filter lives in the same URL but is
// owned by use-catalog-query.ts, and this store neither reads nor writes it:
// two owners of one parameter is the race D-2 exists to prevent.
import { create } from "zustand";

export interface ViewerUrlState {
  paper: string | null;
  page: number | null;
}

const DEFAULT_STATE: ViewerUrlState = { paper: null, page: null };

function parseIntParam(raw: string | null): number | null {
  if (raw === null) return null;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

/** URL -> state half of D-2's symmetry. A malformed page falls back to null
 * rather than throwing: a hand-edited URL degrades, it does not crash. */
export function viewerStateFromSearchParams(params: URLSearchParams): ViewerUrlState {
  return { paper: params.get("paper"), page: parseIntParam(params.get("page")) };
}

/** state -> URL half, the exact inverse for the two keys this store owns.
 * Every OTHER parameter in `base` (the list's filter) passes through
 * untouched, so opening and closing a paper returns the reader to the list
 * they left rather than an unfiltered one. Empty values are omitted, never
 * written as `paper=`. */
export function searchParamsFromViewerState(
  state: ViewerUrlState,
  base: URLSearchParams = new URLSearchParams(),
): URLSearchParams {
  const params = new URLSearchParams(base);
  params.delete("paper");
  params.delete("page");
  if (state.paper) params.set("paper", state.paper);
  if (state.page !== null) params.set("page", String(state.page));
  return params;
}

export interface ViewerStoreState extends ViewerUrlState {
  // Card click: sets the open paper and, unless given, clears the page — a
  // freshly opened paper has no page anchor yet.
  setPaper: (paper: string | null, page?: number | null) => void;
  setPage: (page: number | null) => void;
  // The ONLY setter that writes state from outside a UI intent — called by
  // use-viewer-url-sync.ts when the browser URL changes (nav, back/forward,
  // a pasted link), never by a component reacting to user input.
  hydrateFromUrl: (params: URLSearchParams) => void;
  // Applies one CONFIRMED drive_ui reader action (D-1/D-3, issue #32) — called
  // only by hooks/use-drive-ui.ts. drive_ui.py already validated the target
  // against the indexed set; this only shapes args onto the store. goto_page
  // sets paper+page in ONE call so use-viewer-url-sync.ts pushes one URL for
  // the pair. `set_filters` is not handled here: the filter is the list's,
  // and use-drive-ui.ts writes it to the URL directly.
  applyDriveAction: (action: string, args: Record<string, unknown>) => void;
  reset: () => void;
}

function stringArg(args: Record<string, unknown>, key: string): string | null {
  const value = args[key];
  return typeof value === "string" ? value : null;
}

function numberArg(args: Record<string, unknown>, key: string): number | null {
  const value = args[key];
  return typeof value === "number" ? value : null;
}

export const useViewerStore = create<ViewerStoreState>()((set) => ({
  ...DEFAULT_STATE,

  setPaper: (paper, page = null) => set({ paper, page }),

  setPage: (page) => set({ page }),

  hydrateFromUrl: (params) => set(viewerStateFromSearchParams(params)),

  applyDriveAction: (action, args) =>
    set(() => {
      switch (action) {
        case "open_paper": {
          const paperId = stringArg(args, "paper_id");
          return paperId ? { paper: paperId, page: null } : {};
        }
        case "goto_page": {
          const paperId = stringArg(args, "paper_id");
          const page = numberArg(args, "page");
          return paperId && page !== null ? { paper: paperId, page } : {};
        }
        default:
          // Forward-compat: an action this store does not own, mirroring
          // agent-session-store.ts's own applyEvent default case.
          return {};
      }
    }),

  reset: () => set(DEFAULT_STATE),
}));
