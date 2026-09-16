"use client";

import { useVirtualizer, type VirtualItem } from "@tanstack/react-virtual";
import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";

/** The paging half of an infinite query, as the list needs it. Passing the
 * error flag is what stops a failed page from being re-requested on every
 * render: the list stops asking and the caller shows a retry. */
export type NextPage = {
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFetchNextPageError: boolean;
  fetchNextPage: (options?: { cancelRefetch?: boolean }) => unknown;
};

/** A windowed list over an infinite query: only the rows near the viewport
 * are in the DOM, and the next page is asked for before the reader reaches
 * the end (D-1).
 *
 * Two list shapes use it. The /app explorer scrolls its own box, so the list
 * starts at offset 0 of its scroller. The catalog lives inside a page-length
 * canvas under a heading and a sticky search, so the scroller is an ancestor
 * and the list starts partway down it; pass `listRef` and its offset is
 * measured into `scrollMargin`, which the virtualizer needs to know which
 * rows are on screen.
 *
 * Rows are measured, not assumed: titles wrap from one line to five, and a
 * fixed height overlaps the next row the moment real content exceeds it.
 * `estimateSize` only seeds the layout before the first measurement.
 *
 * `resetKey` is the query's identity. When it changes the list is a
 * different list, so the scroller goes back to the top instead of leaving
 * the reader at row 400 of a result that now has 12.
 *
 * `rememberAs` keeps the reader's place across a trip away and back: open a
 * paper in the reader, press Back, and the list is where it was rather than
 * at the top. The canvas is an inner scroller, so the browser's own scroll
 * restoration never sees it. The place is the library's snapshot of measured
 * rows plus the offset (TanStack Virtual's documented restore), stored per
 * tab and per query. It is only used when the rows it describes are already
 * back from the query cache on mount; a place in a list that is not there
 * yet would scroll into blank space.
 */
export function useInfiniteVirtualList({
  count,
  scrollElement,
  listRef,
  estimateSize,
  overscan,
  gap = 0,
  fetchAhead,
  page,
  resetKey,
  rememberAs,
}: {
  count: number;
  /** The scroller itself, held in its owner's state rather than a ref. A
   * parent's ref is attached after a child's layout effects run, so a list
   * that mounts in the same commit as its scroller (Explore, reopened with
   * its first page already cached) read `null`, and nothing re-rendered to
   * make it look again: the list kept its height and drew no rows. A node
   * in state re-renders the list the moment it exists. */
  scrollElement: HTMLElement | null;
  listRef?: RefObject<HTMLElement | null>;
  estimateSize: number;
  overscan: number;
  gap?: number;
  /** How many rows before the end of what is loaded the next page is asked for. */
  fetchAhead: number;
  page: NextPage;
  resetKey: string;
  /** Session-storage namespace for the scroll place; omit to not keep one. */
  rememberAs?: string;
}) {
  const placeKey = rememberAs ? `${rememberAs}:${resetKey}` : null;
  const [restored] = useState(() => readPlace(placeKey, count));
  const scrollMargin = useListOffset(scrollElement, listRef, count > 0, restored?.margin ?? 0);

  const virtualizer = useVirtualizer({
    count,
    getScrollElement: () => scrollElement,
    estimateSize: () => estimateSize,
    overscan,
    gap,
    scrollMargin,
    initialOffset: restored?.offset ?? 0,
    initialMeasurementsCache: restored?.rows,
  });
  const items = virtualizer.getVirtualItems();
  const lastIndex = items[items.length - 1]?.index ?? -1;

  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = page;
  useEffect(() => {
    if (lastIndex < 0 || lastIndex < count - 1 - fetchAhead) return;
    if (!hasNextPage || isFetchingNextPage || isFetchNextPageError) return;
    // The flags above lag a render behind the request, so two scroll frames
    // can both get here. TanStack's default then cancels the page in flight
    // and asks again (measured: offset 90 requested twice, 59ms apart); this
    // joins the running request instead.
    void fetchNextPage({ cancelRefetch: false });
  }, [
    lastIndex,
    count,
    fetchAhead,
    hasNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
    fetchNextPage,
  ]);

  const seenKey = useRef(resetKey);
  useLayoutEffect(() => {
    if (seenKey.current === resetKey) return;
    seenKey.current = resetKey;
    if (scrollElement) scrollElement.scrollTop = 0;
  }, [resetKey, scrollElement]);

  // Written on the way out, under the key current at that moment. A filter
  // change resets to the top anyway, so only the last query's place matters.
  const latest = useRef({ placeKey, virtualizer, scrollMargin, count });
  useLayoutEffect(() => {
    latest.current = { placeKey, virtualizer, scrollMargin, count };
  });
  useEffect(() => {
    const save = () => {
      const { placeKey: key, virtualizer: v, scrollMargin: margin, count: rows } = latest.current;
      if (!key) return;
      writePlace(key, {
        offset: v.scrollOffset ?? 0,
        margin,
        count: rows,
        rows: v.takeSnapshot(),
      });
    };
    window.addEventListener("pagehide", save);
    return () => {
      window.removeEventListener("pagehide", save);
      save();
    };
  }, []);

  return { virtualizer, items, scrollMargin };
}

type Place = { offset: number; margin: number; count: number; rows: VirtualItem[] };

const PLACE_PREFIX = "virtual-list-place:";

// Storage can be absent or refuse (private windows, blocked site data). A
// lost scroll place is a list that opens at the top, which is where it
// opened before this existed, so a failure here is not worth surfacing.
function readPlace(key: string | null, count: number): Place | null {
  if (!key) return null;
  let place: Place | null = null;
  try {
    const raw = window.sessionStorage.getItem(PLACE_PREFIX + key);
    place = raw ? (JSON.parse(raw) as Place) : null;
  } catch {
    return null;
  }
  if (!place || place.count === 0 || place.count > count) return null;
  return place;
}

function writePlace(key: string, place: Place) {
  try {
    window.sessionStorage.setItem(PLACE_PREFIX + key, JSON.stringify(place));
  } catch {
    // See readPlace.
  }
}

/** Where the list starts inside its scroller, in scroller content pixels.
 *
 * Re-measured whenever the scroller's content changes size, because what
 * sits above the list does: the heading wraps to two lines at phone width,
 * and a font arriving late moves everything below it. */
function useListOffset(
  scroller: HTMLElement | null,
  listRef: RefObject<HTMLElement | null> | undefined,
  // The list element may only mount once there are rows to put in it.
  mounted: boolean,
  // The offset last seen, so a restored place is not read against 0 for the
  // frame before the first measurement.
  initial: number,
): number {
  const [offset, setOffset] = useState(initial);

  useLayoutEffect(() => {
    const list = listRef?.current;
    if (!scroller || !list) return;
    const measure = () => {
      const next = Math.round(
        list.getBoundingClientRect().top -
          scroller.getBoundingClientRect().top +
          scroller.scrollTop,
      );
      setOffset((current) => (current === next ? current : next));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(scroller);
    for (const child of scroller.children) observer.observe(child);
    return () => observer.disconnect();
  }, [scroller, listRef, mounted]);

  return offset;
}
