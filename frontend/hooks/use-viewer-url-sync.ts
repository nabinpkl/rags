"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  searchParamsFromViewerState,
  useViewerStore,
  viewerStateFromSearchParams,
} from "@/stores/viewer-store";

/** The store<->URL glue (D-2, decisions.md): `viewer-store.ts` holds the pure
 * state and the pure URL<->state functions (tested directly, no router
 * needed); this hook is the thin, framework-bound wiring that calls them
 * from a live browser URL — `next/navigation`'s router hooks only run
 * inside a component, so this can't live in the store itself.
 *
 * ONE effect, not two. An earlier version split URL->store and store->URL
 * into separate effects; on initial mount with URL params already present,
 * the store->URL effect ran with a STALE pre-hydration closure right after
 * the URL->store effect's `hydrateFromUrl` call (the store update is
 * scheduled, not synchronous, so the second effect's captured `q`/
 * `category`/... in the same passive-effect flush were still the old
 * defaults) — it would `router.replace` the just-hydrated params away, then
 * self-correct one render later. A single effect makes "which side changed"
 * an atomic decision per flush: if the URL and the store-derived URL already
 * agree, do nothing; otherwise treat an unrecognized URL as the external
 * change (hydrate) and a recognized-but-stale one as the store-driven change
 * (push) — never both in the same pass. */
export function useViewerUrlSync(): void {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const lastSynced = useRef<string | null>(null);

  const { q, category, yearFrom, yearTo, sort, paper, page, hydrateFromUrl } = useViewerStore();

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
      lastSynced.current = urlString;
      return;
    }

    if (urlString !== lastSynced.current) {
      // The URL changed out from under the store: browser back/forward, a
      // pasted link, or a drive_ui-driven push once #29 lands.
      lastSynced.current = urlString;
      hydrateFromUrl(searchParams);
      return;
    }

    // The store changed from a UI intent. `router.push` (not `replace`) so
    // each filter/search/paper change is back-button-navigable, per §4c
    // decision 2's explicit "shareable/back-button friendly" requirement —
    // `replace` would overwrite the previous URL, making the back button a
    // no-op the moment any filter changes. History isn't spammed by this:
    // every UI surface that writes here already debounces or fires once per
    // deliberate action (corpus-search-bar.tsx's `q`, facet-filters.tsx's
    // year inputs; category clicks and row clicks are already one push per
    // click, not per keystroke).
    lastSynced.current = storeString;
    router.push(storeString ? `${pathname}?${storeString}` : pathname, { scroll: false });
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
