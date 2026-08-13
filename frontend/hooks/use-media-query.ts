"use client";

import { useCallback, useSyncExternalStore } from "react";

/** Subscribes to a CSS media query.
 *
 * `useSyncExternalStore` rather than useState+useEffect: the static export
 * prerenders this HTML at build time, where `window` does not exist, and
 * this hook's answer changes ARIA semantics (see lib/breakpoints.ts). The
 * server snapshot is deliberately `false` — "not docked", i.e. the drawer
 * reading — because that is the accessible-by-default answer: a drawer
 * carries a dialog's semantics and a close button, which are harmless if
 * the first client paint corrects to docked, whereas prerendering "docked"
 * and correcting to "drawer" would briefly leave an open overlay with no
 * labelled way out.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === "undefined") return () => {};
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );

  const getSnapshot = useCallback(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  }, [query]);

  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
