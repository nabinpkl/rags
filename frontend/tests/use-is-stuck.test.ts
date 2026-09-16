import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIsStuck } from "@/hooks/use-is-stuck";

type Callback = (entries: Partial<IntersectionObserverEntry>[]) => void;

let fire: Callback = () => {};
let options: IntersectionObserverInit | undefined;
let created = 0;
const disconnect = vi.fn();

class ObserverSpy {
  constructor(callback: Callback, init?: IntersectionObserverInit) {
    fire = callback;
    options = init;
    created += 1;
  }
  observe() {}
  disconnect = disconnect;
}

function refs() {
  const root = document.createElement("main");
  const sentinel = document.createElement("div");
  root.append(sentinel);
  return { sentinel: { current: sentinel }, root: { current: root } };
}

describe("useIsStuck", () => {
  afterEach(() => {
    // Unmount before resetting the counters: Testing Library's own cleanup
    // runs after this hook, so a previous test's disconnect would otherwise
    // land in the next test's count.
    cleanup();
    vi.unstubAllGlobals();
    disconnect.mockClear();
    created = 0;
  });

  it("is pinned exactly while the resting point is out of the scroller", () => {
    vi.stubGlobal("IntersectionObserver", ObserverSpy);
    const { sentinel, root } = refs();
    const { result } = renderHook(() => useIsStuck(sentinel, root));

    expect(result.current).toBe(false);
    expect(options?.root).toBe(root.current);

    act(() => fire([{ isIntersecting: false }]));
    expect(result.current).toBe(true);

    act(() => fire([{ isIntersecting: true }]));
    expect(result.current).toBe(false);
  });

  it("leaves no observer running when the page goes away", () => {
    vi.stubGlobal("IntersectionObserver", ObserverSpy);
    const { sentinel, root } = refs();
    const { unmount } = renderHook(() => useIsStuck(sentinel, root));

    unmount();

    expect(created).toBe(1);
    expect(disconnect).toHaveBeenCalledTimes(1);
  });
});
