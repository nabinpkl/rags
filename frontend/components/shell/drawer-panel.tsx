"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { useMediaQuery } from "@/hooks/use-media-query";
import { MEDIA_AGENT_DOCKED, MEDIA_FILTERS_DOCKED } from "@/lib/breakpoints";
import { cn } from "@/lib/utils";

/** A panel that is a docked column on a wide viewport and a slide-over
 * drawer on a narrow one — as ONE element wrapping ONE child instance.
 *
 * That single-instance requirement is why this isn't the obvious
 * `{isMobile ? <Sheet><Chat/></Sheet> : <Column><Chat/></Column>}`: the agent
 * panel owns the app's only SSE subscription (use-agent-stream.ts) and the
 * facet rail owns debounced filter inputs, so mounting either twice — or
 * remounting it on a rotation — would open a second stream or drop a
 * half-typed year. CSS moves the box; React never re-parents it.
 *
 * Closed drawers are `invisible`, not merely translated off-screen: a
 * translated panel keeps its links and inputs in the tab order, so a
 * keyboard user would tab into an agent composer sitting outside the
 * viewport. `visibility` also animates discretely, so the slide still reads
 * as a slide.
 */

// Tailwind scans for literal class strings, so the docked variants are spelled
// out per breakpoint rather than interpolated — and each sits next to the media
// query JS uses for the same threshold, so the two can't drift apart.
const DOCK = {
  md: {
    media: MEDIA_FILTERS_DOCKED,
    classes: "md:static md:visible md:z-auto md:translate-x-0 md:shadow-none",
  },
  lg: {
    media: MEDIA_AGENT_DOCKED,
    classes: "lg:static lg:visible lg:z-auto lg:translate-x-0 lg:shadow-none",
  },
} as const;

const SIDE = {
  left: { anchor: "left-0", closed: "-translate-x-full" },
  right: { anchor: "right-0", closed: "translate-x-full" },
} as const;

interface DrawerPanelProps {
  /** Viewport width at which this panel stops being a drawer and docks. */
  dockAt: keyof typeof DOCK;
  side: keyof typeof SIDE;
  /** Accessible name — the region's label when docked, the dialog's when not. */
  label: string;
  open: boolean;
  onClose: () => void;
  /** Width/appearance classes; the caller owns size, this owns position. */
  className?: string;
  children: ReactNode;
}

export function DrawerPanel({
  dockAt,
  side,
  label,
  open,
  onClose,
  className,
  children,
}: DrawerPanelProps) {
  const dock = DOCK[dockAt];
  const docked = useMediaQuery(dock.media);
  const asDrawer = !docked;
  const overlaying = asDrawer && open;
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!overlaying) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [overlaying, onClose]);

  // Focus enters the panel on open and returns to the trigger on close —
  // without this a drawer opened from the keyboard leaves focus behind it on
  // the page underneath, and closing strands it on a now-invisible element.
  useEffect(() => {
    if (!overlaying) return;
    restoreFocusTo.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => restoreFocusTo.current?.focus?.();
  }, [overlaying]);

  return (
    <>
      {overlaying && (
        <button
          type="button"
          aria-label={`Close ${label}`}
          onClick={onClose}
          className="bg-ink/40 fixed inset-0 z-30 cursor-default"
        />
      )}
      <div
        ref={panelRef}
        // Dialog semantics belong to the drawer only. Docked, this is just a
        // column of the page — announcing it as a modal dialog would tell a
        // screen-reader user the rest of the app is inert when it isn't.
        {...(asDrawer
          ? { role: "dialog" as const, "aria-modal": true, tabIndex: -1 }
          : { role: "region" as const })}
        aria-label={label}
        className={cn(
          "fixed inset-y-0 z-40 flex flex-col shadow-2xl transition-transform duration-200 motion-reduce:transition-none",
          SIDE[side].anchor,
          open ? "visible translate-x-0" : cn("invisible", SIDE[side].closed),
          dock.classes,
          className,
        )}
      >
        {children}
      </div>
    </>
  );
}
