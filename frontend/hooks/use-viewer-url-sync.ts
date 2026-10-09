"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  searchParamsFromViewerState,
  useViewerStore,
  viewerStateFromSearchParams,
} from "@/stores/viewer-store";

/** The store<->URL glue for the reader (D-2, DECISIONS.md): `viewer-store.ts`
 * holds the pure state and the pure URL<->state functions; this hook is the
 * thin, framework-bound wiring, because next/navigation's router hooks only
 * run inside a component.
 *
 * It compares and writes only `paper` and `page`. The list's filter shares
 * the URL and belongs to use-catalog-query.ts: a push here carries the live
 * filter parameters through unchanged, and a filter change there is not a
 * viewer change here, so neither owner can undo the other.
 *
 * ONE effect, not two (an earlier two-effect version raced a stale
 * pre-hydration closure on initial mount — see git history / DECISIONS.md).
 *
 * Classification is by `prevStoreString` (what the STORE said last time this
 * effect ran), not by comparing the live URL against the hook's own last push
 * (review round 1, PR #68 [major]): after `router.push`, `searchParams` lags
 * the pushed URL until Next commits the navigation, often several ticks. A
 * second store-driven change inside that window would otherwise look like an
 * external URL change and be reverted by a hydrate against the stale URL.
 * A mismatch between the current and previous store strings can only mean
 * the store changed, whatever the live URL currently says. */
export function useViewerUrlSync(): void {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const { paper, page, hydrateFromUrl } = useViewerStore();

  // Seeded from the CURRENT store on first render: the first effect run then
  // reads a URL with `paper` against a still-default store as an external
  // change (hydrate), not as a store-driven push that would erase it.
  const prevStoreString = useRef(searchParamsFromViewerState({ paper, page }).toString());

  useEffect(() => {
    const urlString = searchParamsFromViewerState(
      viewerStateFromSearchParams(searchParams),
    ).toString();
    const storeString = searchParamsFromViewerState({ paper, page }).toString();

    if (urlString === storeString) {
      prevStoreString.current = storeString;
      return;
    }

    if (storeString !== prevStoreString.current) {
      // The store changed since this effect last ran: a card click, the
      // reader's back control, or a confirmed drive_ui action. `push`, not
      // `replace`, so opening a paper is one back-button step (§4c decision
      // 2: shareable and back-button friendly).
      prevStoreString.current = storeString;
      const next = searchParamsFromViewerState({ paper, page }, searchParams).toString();
      router.push(next ? `${pathname}?${next}` : pathname, { scroll: false });
      return;
    }

    // The store is unchanged but the URL disagrees: back/forward, a pasted
    // link, or a filter write that dropped `paper`. The re-run after this
    // set() is what advances prevStoreString, to what the store settled on.
    hydrateFromUrl(searchParams);
  }, [searchParams, paper, page, pathname, router, hydrateFromUrl]);
}
