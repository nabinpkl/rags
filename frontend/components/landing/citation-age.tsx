import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { LandingResponse } from "@/lib/api-client";

/** How old the cited work is, as a share of every placeable citation.
 *
 * The claim is made against the COHORT's own year, not a round number: most
 * of a 2026 cohort's citations point at work from before 2026. Undated works
 * count as older.
 */
export function CitationAge({
  stats,
  citedYears,
}: {
  stats: LandingResponse["stats"];
  citedYears: LandingResponse["cited_years"];
}) {
  // An empty graph is a real state (a corpus built before extract_citations
  // ran): keep the raw total to detect it and guard the divisor separately,
  // since "0% of these citations" reads as a finding when it is an absence.
  const placeable = citedYears.reduce((sum, bucket) => sum + bucket.citations, 0);
  const total = placeable || 1;
  // Only the recent tail is legible as bars; the long pre-2020 tail lives in
  // the summary line.
  const recent = citedYears.filter((bucket) => bucket.year !== null && bucket.year >= 2020);
  const max = Math.max(...recent.map((bucket) => bucket.citations), 1);
  const cohortYear = stats.cohort_end ? 2000 + Number(stats.cohort_end.slice(0, 2)) : null;
  const older = cohortYear
    ? citedYears
        .filter((bucket) => bucket.year === null || bucket.year < cohortYear)
        .reduce((sum, bucket) => sum + bucket.citations, 0)
    : 0;

  return (
    <DashboardPanel
      title="How far back it reaches"
      description={
        cohortYear && placeable
          ? `${Math.round((older / total) * 100)}% of citations point at work from before ${cohortYear}.`
          : "No citations to place in time yet."
      }
    >
      <div className="flex min-h-[150px] flex-1 items-end gap-1.5" aria-hidden>
        {recent.map((bucket) => (
          <div key={bucket.year} className="flex h-full flex-1 flex-col items-center gap-1">
            <span className="text-muted font-mono text-[10px] tabular-nums">
              {Math.round((bucket.citations / total) * 100)}%
            </span>
            {/* Percentage of the track, so the chart fills whatever height
                the row hands it instead of ending in a band of empty panel
                beside a taller neighbour. */}
            <div className="relative w-full flex-1">
              <div
                className="bg-chart-1 absolute inset-x-0 bottom-0 rounded-t-sm"
                style={{ height: `${Math.max((bucket.citations / max) * 100, 1.5)}%` }}
              />
            </div>
            <span className="text-muted font-mono text-[10px]">{bucket.year}</span>
          </div>
        ))}
      </div>
    </DashboardPanel>
  );
}
