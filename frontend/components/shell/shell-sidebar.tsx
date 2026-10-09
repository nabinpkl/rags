"use client";

import { ChartNoAxesColumn, Library, MessagesSquare, Quote, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { BrandMark } from "@/components/shell/brand-mark";
import { cn } from "@/lib/utils";

/** The app's reading surfaces, one route each: the whole catalog (home),
 * the citation counts, arXiv's category census, the RAG demo (the indexed
 * papers with the agent that reads them), and the retrieval benchmark.
 *
 * The rail addresses ROUTES, not bands of a scrolling canvas. It used to do
 * both: four rows that scroll-spied the dashboard's bands, and a fifth,
 * separated and captioned, that left the page entirely. Two kinds of target
 * wearing the same row is a rail the reader has to read before clicking, and
 * the band rows were the weaker half — the canvas is four panels tall, so
 * scrolling finds them faster than aiming at a row does.
 */
export const VIEWS = [
  { id: "explore", label: "Explore", href: "/", icon: Library },
  { id: "citations", label: "Citations", href: "/citations", icon: Quote },
  { id: "trends", label: "Trends", href: "/trends", icon: TrendingUp },
  { id: "demo", label: "RAG Demo", href: "/demo", icon: MessagesSquare },
  { id: "benchmarks", label: "Benchmarks", href: "/benchmarks", icon: ChartNoAxesColumn },
] as const satisfies readonly { id: string; label: string; href: string; icon: LucideIcon }[];

export type ShellView = (typeof VIEWS)[number]["id"];

/** The one rail both routes hang off: what this is, which view, and whatever
 * that view needs to steer itself.
 *
 * `children` is the steering slot, filled by the two list views — the
 * catalog's filter lives BELOW the view it filters, in the same column,
 * because a filter is a property of the list rather than a place to go. The
 * alternative was a second rail beside the first, which is two columns of
 * chrome on a 768px viewport before any papers appear.
 */
export function ShellSidebar({ current, children }: { current: ShellView; children?: ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-line flex h-[57px] shrink-0 items-center gap-2.5 border-b px-4">
        <BrandMark />
      </div>

      {/* Nav and filter scroll as one column. They are not peers competing
          for height: the nav is three rows tall and never grows, so a scroll
          container of its own would only ever clip the filter. */}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <nav aria-label="Views" className="shrink-0 p-2">
          <ul className="flex flex-col gap-0.5">
            {VIEWS.map((view) => {
              const active = view.id === current;
              return (
                <li key={view.id}>
                  <Link
                    href={view.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-[13px] transition-colors motion-reduce:transition-none",
                      // Both branches carry a hover: the current row is still
                      // a target, and it steps AWAY from the resting surface
                      // rather than toward it.
                      active
                        ? "bg-teal-soft text-teal-ink hover:bg-teal-soft-strong font-semibold"
                        : "text-ink hover:bg-panel-hover",
                    )}
                  >
                    <view.icon
                      className={cn("size-4 shrink-0", active ? "text-teal-ink" : "text-muted")}
                      aria-hidden
                    />
                    {view.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Same 8px inset as the nav rows above, so the controls line up with
            the pill a selected row draws rather than sitting 4px inside it. */}
        {children && <div className="border-line mt-1 border-t px-2 py-3">{children}</div>}
      </div>
    </div>
  );
}
