"use client";

import { type RefObject, useEffect, useState } from "react";

/** Whether a `position: sticky` element is currently pinned.
 *
 * CSS can answer this itself (`scroll-state(stuck: top)` container queries),
 * but only in Chromium, and the thing that depends on the answer — the edge
 * under the pinned catalog search — should not exist in one engine only.
 *
 * The caller places `sentinelRef` where the sticky element's top edge rests,
 * inside the same scroller; the element is pinned exactly when that point has
 * scrolled out of `rootRef`. An observer rather than a scroll listener, so
 * nothing runs per frame while the reader scrolls a long list.
 */
export function useIsStuck(
  sentinelRef: RefObject<HTMLElement | null>,
  rootRef: RefObject<HTMLElement | null>,
): boolean {
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    const root = rootRef.current;
    if (!sentinel || !root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[entries.length - 1];
        if (entry) setStuck(!entry.isIntersecting);
      },
      { root },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [sentinelRef, rootRef]);

  return stuck;
}
