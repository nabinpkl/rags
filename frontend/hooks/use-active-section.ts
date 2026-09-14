"use client";

import { type RefObject, useEffect, useState } from "react";

/** How far below the canvas's top edge a band's heading has to pass before it
 * counts as the one being read. Roughly one panel header. */
const HANDOVER_LINE_PX = 96;

/** Which dashboard band the reader is currently looking at.
 *
 * Read from scroll position rather than from the last click, because arriving
 * by wheel, by keyboard, and by rail click all have to light the same row — a
 * rail that only updates on its own clicks is decoration, and is exactly what
 * makes a page with a sidebar still not read as a dashboard.
 *
 * Geometry per scroll rather than an IntersectionObserver band: the final
 * band is usually shorter than the canvas, so no scroll position ever carries
 * its top across an observer's strip and the rail goes dead exactly where the
 * reader can see it is wrong. Hitting the end of the scroll is the only honest
 * answer there, and that is a scroll-position fact, not an intersection.
 */
export function useActiveSection(
  ids: readonly string[],
  rootRef: RefObject<HTMLElement | null>,
  /** False while the bands are unmounted (loading, or a detail view is open);
   * flipping it back re-measures against the nodes the new commit created. */
  enabled = true,
): string | null {
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!enabled || !root) return;

    let frame = 0;

    function measure() {
      frame = 0;
      if (!root) return;
      const line = root.getBoundingClientRect().top + HANDOVER_LINE_PX;
      let current = ids[0] ?? null;
      for (const id of ids) {
        const node = document.getElementById(id);
        if (node && node.getBoundingClientRect().top <= line) current = id;
      }
      // Within a pixel of the end, the last band is the answer whatever the
      // line says: there is no scroll left to bring it up any further.
      if (root.scrollTop + root.clientHeight >= root.scrollHeight - 1) {
        current = ids[ids.length - 1] ?? current;
      }
      setActive(current);
    }

    function schedule() {
      if (!frame) frame = requestAnimationFrame(measure);
    }

    // Scheduled rather than called: an effect that sets state in its own body
    // queues a second render before paint (react-hooks/set-state-in-effect).
    schedule();
    root.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      root.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, [ids, rootRef, enabled]);

  return active;
}
