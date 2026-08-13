// This hook decides whether a panel is announced as a docked region or a
// modal dialog (drawer-panel.tsx), so a stale answer is an accessibility bug,
// not a cosmetic one: the tests below pin that it tracks CHANGES and that it
// detaches its listener.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useMediaQuery } from "@/hooks/use-media-query";

interface FakeList {
  matches: boolean;
  listeners: Set<() => void>;
}

function installMatchMedia(initial: boolean) {
  const list: FakeList = { matches: initial, listeners: new Set() };
  const removeSpy = vi.fn();
  vi.stubGlobal("matchMedia", (query: string) => ({
    media: query,
    get matches() {
      return list.matches;
    },
    addEventListener: (_: string, cb: () => void) => list.listeners.add(cb),
    removeEventListener: (_: string, cb: () => void) => {
      removeSpy();
      list.listeners.delete(cb);
    },
  }));
  return {
    removeSpy,
    set(matches: boolean) {
      list.matches = matches;
      for (const cb of list.listeners) cb();
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMediaQuery", () => {
  it("reports the query's initial state", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(true);
  });

  it("re-renders when the viewport crosses the breakpoint", () => {
    const mm = installMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(false);

    act(() => mm.set(true));
    expect(result.current).toBe(true);

    act(() => mm.set(false));
    expect(result.current).toBe(false);
  });

  it("removes its listener on unmount", () => {
    const mm = installMatchMedia(true);
    const { unmount } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    unmount();
    expect(mm.removeSpy).toHaveBeenCalled();
  });
});
