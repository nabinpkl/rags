"use client";

import { useQuery } from "@tanstack/react-query";

import { CategoryCensus } from "@/components/landing/category-census";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { fetchCategoryCensus } from "@/lib/api-client";

/** What arXiv cs posted, by primary category, month by month. A STATIC route
 * (§4c decision 2, amended 2026-10-02).
 *
 * Kept apart from Citations because it answers a different question: every
 * other count on the site is over papers WE hold, and this one is a census of
 * what arXiv announced, drawn only for months we hold whole.
 */
export default function TrendsPage() {
  const {
    data: census,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["census"],
    queryFn: fetchCategoryCensus,
  });

  return (
    <DashboardShell current="trends" trail={<li className="text-ink font-medium">Trends</li>}>
      <div className="pt-2 pb-1">
        <h1 className="font-serif text-ink max-w-[24ch] text-[clamp(1.7rem,3.4vw,2.35rem)] leading-[1.1] font-bold text-balance">
          What computer science is publishing
        </h1>
        <p className="text-ink-2 mt-3 max-w-[60ch] text-[15px] leading-snug">
          Share of every cs paper arXiv announced, by primary category.
        </p>
      </div>

      {isPending && <p className="text-muted py-16 text-center">Loading the census…</p>}
      {isError && (
        <p className="text-muted py-16 text-center">
          Could not reach the corpus. The API may still be starting up.
        </p>
      )}
      {/* Capped: the table has a column per month, and at the canvas's full
          width two columns of bars sat half a screen apart. */}
      {census && (
        <div className="max-w-[860px]">
          <CategoryCensus census={census} />
        </div>
      )}
    </DashboardShell>
  );
}
