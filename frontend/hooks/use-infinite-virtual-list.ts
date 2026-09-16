"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
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
 */
export function useInfiniteVirtualList({
  count,
  scrollRef,
  listRef,
  estimateSize,
  overscan,
  gap = 0,
  fetchAhead,
  page,
  resetKey,
}: {
  count: number;
  scrollRef: RefObject<HTMLElement | null>;
  listRef?: RefObject<HTMLElement | null>;
  estimateSize: number;
  overscan: number;
  gap?: number;
  /** How many rows before the end of what is loaded the next page is asked for. */
  fetchAhead: number;
  page: NextPage;
  resetKey: string;
}) {
  const scrollMargin = useListOffset(scrollRef, listRef, count > 0);

  const virtualizer = useVirtualizer({
    count,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => estimateSize,
    overscan,
    gap,
    scrollMargin,
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
    const scroller = scrollRef.current;
    if (scroller) scroller.scrollTop = 0;
  }, [resetKey, scrollRef]);

  return { virtualizer, items, scrollMargin };
}

/** Where the list starts inside its scroller, in scroller content pixels.
 *
 * Re-measured whenever the scroller's content changes size, because what
 * sits above the list does: the heading wraps to two lines at phone width,
 * and a font arriving late moves everything below it. */
function useListOffset(
  scrollRef: RefObject<HTMLElement | null>,
  listRef: RefObject<HTMLElement | null> | undefined,
  // The list element may only mount once there are rows to put in it.
  mounted: boolean,
): number {
  const [offset, setOffset] = useState(0);

  useLayoutEffect(() => {
    const scroller = scrollRef.current;
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
  }, [scrollRef, listRef, mounted]);

  return offset;
}
