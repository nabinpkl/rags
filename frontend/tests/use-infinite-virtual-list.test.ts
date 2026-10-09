import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
  return element;
}

function props(overrides: Partial<Parameters<typeof useInfiniteVirtualList>[0]>) {
  return {
    count: 3,
    scrollElement: scroller(),
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

  it("draws rows once the scroller exists, when it did not on the first render", () => {
    // Regression: Explore reopened with a cached first page mounts the list in
    // the same commit as its scroller, so the first render has no scroller.
    const canvas = scroller();
    const { result, rerender } = renderHook((p) => useInfiniteVirtualList(p), {
      initialProps: props({ scrollElement: null, count: 30 }),
    });
    expect(result.current.items).toHaveLength(0);

    rerender(props({ scrollElement: canvas, count: 30 }));
    expect(result.current.items.length).toBeGreaterThan(0);
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
    const canvas = scroller(900);
    const { rerender } = renderHook((p) => useInfiniteVirtualList(p), {
      initialProps: props({ scrollElement: canvas }),
    });
    expect(canvas.scrollTop).toBe(900);

    rerender(props({ scrollElement: canvas, count: 6 }));
    expect(canvas.scrollTop).toBe(900);

    rerender(props({ scrollElement: canvas, count: 6, resetKey: "b" }));
    expect(canvas.scrollTop).toBe(0);
  });

  describe("keeping the reader's place", () => {
    // Unmount first: an unmount is a save, and Testing Library's own cleanup
    // runs after this hook, so the last test's place would outlive the clear.
    afterEach(() => {
      cleanup();
      window.sessionStorage.clear();
    });

    const place = (count: number) => JSON.stringify({ offset: 900, margin: 120, count, rows: [] });

    it("saves the place under the query when the list goes away", () => {
      const { unmount } = renderHook(() =>
        useInfiniteVirtualList(props({ rememberAs: "catalog", resetKey: "q=a" })),
      );
      unmount();

      const saved = JSON.parse(
        window.sessionStorage.getItem("virtual-list-place:catalog:q=a") ?? "null",
      );
      expect(saved).toMatchObject({ offset: 0, count: 3 });
    });

    it("scrolls back to it when the rows are already there", () => {
      window.sessionStorage.setItem("virtual-list-place:catalog:q=a", place(3));
      const canvas = scroller();
      const { result } = renderHook(() =>
        useInfiniteVirtualList(
          props({ scrollElement: canvas, rememberAs: "catalog", resetKey: "q=a" }),
        ),
      );

      expect(canvas.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 900 }));
      expect(result.current.scrollMargin).toBe(120);
    });

    it("starts at the top when the rows it describes have not loaded", () => {
      window.sessionStorage.setItem("virtual-list-place:catalog:q=a", place(90));
      const canvas = scroller();
      renderHook(() =>
        useInfiniteVirtualList(
          props({ scrollElement: canvas, rememberAs: "catalog", resetKey: "q=a" }),
        ),
      );

      expect(canvas.scrollTo).not.toHaveBeenCalledWith(expect.objectContaining({ top: 900 }));
    });

    it("keeps no place for a list that did not ask for one", () => {
      const { unmount } = renderHook(() => useInfiniteVirtualList(props({})));
      unmount();

      expect(window.sessionStorage.length).toBe(0);
    });
  });
});
