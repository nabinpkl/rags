"use client";

import { Activity, FlaskConical, LayoutDashboard, ListOrdered } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Image from "next/image";

import { cn } from "@/lib/utils";

/** The bands of the dashboard, in canvas order.
 *
 * One entry per VERTICAL band, never per panel: two panels that share a grid
 * row also share a scroll offset, so a second entry pointing into the same
 * row would scroll nowhere and light the wrong rail row. If a panel deserves
 * its own rail entry, it deserves its own band.
 */
export const SECTIONS: readonly { id: string; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "foundations", label: "Foundations", icon: ListOrdered },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "methods", label: "Method", icon: FlaskConical },
];

export const SECTION_IDS: readonly string[] = SECTIONS.map((section) => section.id);

/** The dashboard's persistent rail: what this is, where you are, where out.
 *
 * The rows are buttons rather than `#id` links because a foundation's detail
 * replaces the bands entirely — the anchor's target is not in the document at
 * the moment it is clicked, so the caller restores the bands first and scrolls
 * on the commit that brings them back.
 */
export function DashboardSidebar({
  active,
  windowLabel,
  onNavigate,
}: {
  /** Section id the reader is currently looking at, from scroll position. */
  active: string | null;
  windowLabel: string | null;
  onNavigate: (id: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-line flex h-[57px] shrink-0 items-center gap-2.5 border-b px-4">
        {/* The mark is REFERENCED, not redrawn: `app/icon.svg` is the one copy
            of that geometry, and it is already served at /icon.svg by Next's
            metadata convention. A second copy in JSX would drift the first
            time the tab icon changed. */}
        <Image src="/icon.svg" alt="" width={26} height={26} className="rounded-[6px]" />
        <span className="min-w-0">
          <b className="font-serif text-ink block text-[17px] leading-none font-bold">
            ask<em className="text-teal-ink not-italic">RAG</em>
          </b>
          <span className="text-muted mt-1 block font-mono text-[9.5px] tracking-[0.1em] uppercase">
            arXiv cs corpus
          </span>
        </span>
      </div>

      <nav aria-label="Dashboard sections" className="min-h-0 flex-1 overflow-y-auto p-2">
        <p className="text-muted px-2.5 pt-1 pb-2 font-mono text-[9.5px] tracking-[0.14em] uppercase">
          Sections
        </p>
        <ul className="flex flex-col gap-0.5">
          {SECTIONS.map((section) => {
            const current = section.id === active;
            return (
              <li key={section.id}>
                <button
                  type="button"
                  onClick={() => onNavigate(section.id)}
                  aria-current={current ? "true" : undefined}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-[13px] transition-colors motion-reduce:transition-none",
                    // Both branches carry a hover: the current row is still a
                    // target (it scrolls back to the top of its band), and it
                    // steps AWAY from the resting surface rather than toward
                    // it — `--teal-soft-strong` exists for exactly this.
                    current
                      ? "bg-teal-soft text-teal-ink hover:bg-teal-soft-strong font-semibold"
                      : "text-ink hover:bg-paper",
                  )}
                >
                  <section.icon
                    className={cn("size-4 shrink-0", current ? "text-teal-ink" : "text-muted")}
                    aria-hidden
                  />
                  {section.label}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* The dataset's identity, not a control: which slice of arXiv every
          number on the canvas was counted over. The way OUT of the dashboard
          is the top bar's one button — spelling it here too would make the
          rail and the bar compete for the same click. */}
      <dl className="border-line shrink-0 border-t px-4 py-3.5">
        <dt className="text-muted font-mono text-[9.5px] tracking-[0.14em] uppercase">Window</dt>
        <dd className="text-ink mt-1 font-mono text-[11.5px] tabular-nums">
          {windowLabel ?? "not yet counted"}
        </dd>
        <dt className="text-muted mt-3 font-mono text-[9.5px] tracking-[0.14em] uppercase">
          Source
        </dt>
        <dd className="text-ink mt-1 font-mono text-[11.5px]">arXiv cs, parsed references</dd>
      </dl>
    </div>
  );
}
