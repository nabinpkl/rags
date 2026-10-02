import type { CoverageResponse, LandingResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

type Month = CoverageResponse["months"][number];

/** The page's question, one line of scope, and how much of each counted
 * month we hold.
 *
 * The meters replace a paragraph of totals. "27,907 of the 32,519 cs papers"
 * is the same claim as three bars, and the bars also show WHERE the gap is
 * (a month still being collected), which the sentence could not. Citation
 * and cited-work totals are gone: they size our pile, not the finding.
 */
export function Hero({
  stats,
  months,
}: {
  stats: LandingResponse["stats"];
  /** The coverage series; only the cohort's months are drawn. */
  months?: Month[];
}) {
  const { cohort_start: start, cohort_end: end } = stats;
  const cohort =
    start && end ? (months ?? []).filter((m) => m.month >= start && m.month <= end) : [];

  return (
    <div className="@container">
      <div className="flex flex-col gap-5 pt-2 pb-1 @2xl:flex-row @2xl:items-end @2xl:justify-between @2xl:gap-10">
        <div className="min-w-0">
          <h1 className="font-serif text-ink max-w-[24ch] text-[clamp(1.7rem,3.4vw,2.35rem)] leading-[1.1] font-bold text-balance">
            What is computer science building on right now?
          </h1>
          <p className="text-ink-2 mt-3 max-w-[60ch] text-[15px] leading-snug">
            The arXiv work cited most by cs papers posted {formatCohort(stats)}.
          </p>
        </div>

        {cohort.length > 0 && (
          <div className="shrink-0 @2xl:w-[280px]">
            <p className="text-muted mb-2 text-[11.5px]">Share of arXiv cs collected</p>
            <dl className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1.5">
              {cohort.map((month) => {
                const share = month.catalog_papers
                  ? month.papers_held / month.catalog_papers
                  : null;
                const label =
                  share === null
                    ? `${month.papers_held.toLocaleString()} papers`
                    : `${month.papers_held.toLocaleString()} of ${month.catalog_papers?.toLocaleString()} papers`;
                return (
                  <div key={month.month} className="contents" title={label}>
                    <dt className="text-muted font-mono text-[11px] tabular-nums">
                      {formatIdMonth(month.month, "short")}
                    </dt>
                    <dd className="bg-line h-1.5 overflow-hidden rounded-sm">
                      <span
                        className="bg-chart-1 block h-full rounded-sm"
                        style={{ width: `${Math.min((share ?? 0) * 100, 100)}%` }}
                      />
                    </dd>
                    <dd className="text-ink w-10 text-right font-mono text-[11px] tabular-nums">
                      {share === null ? "n/a" : `${Math.round(share * 100)}%`}
                      <span className="sr-only">, {label}</span>
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}

/** "in August 2026" for one month, "from July 2026 to September 2026" for
 * several. Each side carries its OWN year: pinning the start month to the end
 * year once printed "November 2026" for a span beginning in November 2007. */
function formatCohort(stats: LandingResponse["stats"]): string {
  const { cohort_start: start, cohort_end: end } = stats;
  if (!start || !end) return "in the indexed months";
  if (start === end) return `in ${formatIdMonth(end)}`;
  return `from ${formatIdMonth(start)} to ${formatIdMonth(end)}`;
}
