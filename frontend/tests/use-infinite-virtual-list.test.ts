import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type NextPage, useInfiniteVirtualList } from "@/hooks/use-infinite-virtual-list";

const MORE: NextPage = {
  hasNextPage: true,
  isFetchingNextPage: false,
  isFetchNextPageError: false,
  fetchNextPage: () => {},
};

function scroller(scrollTop = 0) {
  const element = document.body.appendChild(document.createElement("div"));
  Object.defineProperty(element, "offsetHeight", { value: 600 });
  Object.defineProperty(element, "offsetWidth", { value: 800 });
  element.scrollTop = scrollTop;
  // The virtualizer scrolls on its own account; only the hook's reset is
  // under test, and that writes `scrollTop`.
  element.scrollTo = vi.fn();
  return { current: element };
}

function props(overrides: Partial<Parameters<typeof useInfiniteVirtualList>[0]>) {
  return {
    count: 3,
    scrollRef: scroller(),
    estimateSize: 50,
    overscan: 2,
    fetchAhead: 1,
    page: MORE,
    resetKey: "a",
    ...overrides,
  };
}

describe("useInfiniteVirtualList", () => {
  it("windows only what is near the viewport", () => {
    const { result } = renderHook(() => useInfiniteVirtualList(props({ count: 1000 })));

    // 600px of 50px rows is 12, plus the overscan: nowhere near 1,000.
    expect(result.current.items.length).toBeGreaterThan(0);
    expect(result.current.items.length).toBeLessThan(20);
  });

  it("does not ask for a page while one is loading, or after one failed", () => {
    const fetchNextPage = vi.fn();
    const { rerender } = renderHook((p) => useInfiniteVirtualList(p), {
      initialProps: props({ page: { ...MORE, isFetchingNextPage: true, fetchNextPage } }),
    });
    rerender(props({ page: { ...MORE, isFetchNextPageError: true, fetchNextPage } }));

    expect(fetchNextPage).not.toHaveBeenCalled();
  });

  it("joins a page already in flight rather than cancelling and re-asking", () => {
    const fetchNextPage = vi.fn();
    renderHook(() => useInfiniteVirtualList(props({ page: { ...MORE, fetchNextPage } })));

    expect(fetchNextPage).toHaveBeenCalledWith({ cancelRefetch: false });
  });

  it("sends the scroller back to the top when the query changes, not when rows arrive", () => {
    const scrollRef = scroller(900);
    const { rerender } = renderHook((p) => useInfiniteVirtualList(p), {
      initialProps: props({ scrollRef }),
    });
    expect(scrollRef.current.scrollTop).toBe(900);

    rerender(props({ scrollRef, count: 6 }));
    expect(scrollRef.current.scrollTop).toBe(900);

    rerender(props({ scrollRef, count: 6, resetKey: "b" }));
    expect(scrollRef.current.scrollTop).toBe(0);
  });
});
