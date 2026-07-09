"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { searchParamsFromViewerState, useViewerStore } from "@/stores/viewer-store";

/** The store<->URL glue (D-2, decisions.md): `viewer-store.ts` holds the pure
 * state and the pure URL<->state functions (tested directly, no router
 * needed); this hook is the thin, framework-bound wiring that calls them
 * from a live browser URL — `next/navigation`'s router hooks only run
 * inside a component, so this can't live in the store itself.
 *
 * ONE effect, not two (an earlier two-effect version raced a stale
 * pre-hydration closure on initial mount — see git history / decisions.md).
 *
 * Classification is by `prevStoreString` (what the STORE said last time this
 * effect ran), not by comparing the live URL against the hook's own last
 * push target (review round 1, PR #68 [major]): after `router.push`,
 * `searchParams` lags the pushed URL until Next commits the navigation —
 * often several ticks, since navigation is async. A second store-driven
 * change landing inside that window would see a `searchParams` value that
 * still reflects the PRE-push URL, indistinguishable by string-vs-live-URL
 * comparison from a genuine external URL change, and would wrongly
 * `hydrateFromUrl` against that stale URL, reverting the second change.
 * Comparing the current store string against the PREVIOUS store string
 * instead needs no dependency on `searchParams` having caught up: a
 * mismatch there can only mean the store changed since we last looked (this
 * hook is the only place that reads `prevStoreString`), so it's
 * unambiguously store-driven regardless of what the live URL currently
 * says. */
export function useViewerUrlSync(): void {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const { q, category, yearFrom, yearTo, sort, paper, page, hydrateFromUrl } = useViewerStore();

  // Seeded from the CURRENT store on first render (not "" / null): on mount,
  // this makes the first effect run compare the live URL against the
  // store's actual starting state, so a URL with params but a still-default
  // store is correctly read as "the store hasn't changed" -> external URL
  // change -> hydrate, not misread as a store-driven push that would
  // overwrite the URL's params with the (still-default) store.
  const prevStoreString = useRef(
    searchParamsFromViewerState({ q, category, yearFrom, yearTo, sort, paper, page }).toString(),
  );

  useEffect(() => {
    const urlString = searchParams.toString();
    const storeString = searchParamsFromViewerState({
      q,
      category,
      yearFrom,
      yearTo,
      sort,
      paper,
      page,
    }).toString();

    if (urlString === storeString) {
      prevStoreString.current = storeString;
      return;
    }

    if (storeString !== prevStoreString.current) {
      // The store changed since this effect last ran — a UI intent (filter
      // click, debounced input commit, row click, or a future drive_ui
      // dispatch once #29 lands). `router.push` (not `replace`) so each
      // change is back-button-navigable, per §4c decision 2's explicit
      // "shareable/back-button friendly" requirement. History isn't spammed:
      // every high-frequency input here already debounces (corpus-search-
      // bar.tsx's `q`, facet-filters.tsx's year inputs); category/row clicks
      // are already one push per deliberate click.
      prevStoreString.current = storeString;
      router.push(storeString ? `${pathname}?${storeString}` : pathname, { scroll: false });
      return;
    }

    // The store is unchanged since last run, but the URL doesn't match it —
    // the URL changed out from under the store: browser back/forward, a
    // pasted link, or a drive_ui-driven push once #29 lands.
    hydrateFromUrl(searchParams);
    // prevStoreString is left as-is: the pending `hydrateFromUrl` set() will
    // update the store, this effect re-runs with the new store values, and
    // that run's `urlString === storeString` branch (above) is what
    // actually advances `prevStoreString` — matching what the store settled
    // to, not what was requested.
  }, [
    searchParams,
    q,
    category,
    yearFrom,
    yearTo,
    sort,
    paper,
    page,
    pathname,
    router,
    hydrateFromUrl,
  ]);
}
