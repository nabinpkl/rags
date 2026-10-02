import type { CoverageResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** How much of each cohort month's cs papers we hold, in the bar's spare
 * width: the catalog's scope, stated where its list is.
 *
 * Only the cohort's months are drawn (the API names them, so the rule that
 * picks them lives once, in `cohort_months`). Everything else is a few papers
 * a month and would draw as a row of empty meters.
 */
export function CoverageStrip({ coverage }: { coverage: CoverageResponse }) {
  const months = coverage.months.filter((month) => coverage.cohort.includes(month.month));
  if (months.length === 0) return null;

  return (
    <div className="flex shrink-0 items-center gap-3">
      <span className="text-muted hidden text-[11px] lg:inline">Collected</span>
      <dl aria-label="Share of arXiv cs papers collected" className="flex items-center gap-3">
        {months.map((month) => {
          const share = month.catalog_papers ? month.papers_held / month.catalog_papers : null;
          const label =
            share === null
              ? `${formatIdMonth(month.month)}: ${month.papers_held.toLocaleString()} papers`
              : `${formatIdMonth(month.month)}: ${month.papers_held.toLocaleString()} of ${month.catalog_papers?.toLocaleString()} papers`;
          return (
            <div key={month.month} className="flex items-center gap-1.5" title={label}>
              {/* The year is dropped on phones, where three full labels
                  crowd the breadcrumb; the tooltip and sr text keep it. */}
              <dt className="text-muted font-mono text-[10.5px] tabular-nums">
                <span className="sm:hidden">
                  {formatIdMonth(month.month, "short").split(" ")[0]}
                </span>
                <span className="hidden sm:inline">{formatIdMonth(month.month, "short")}</span>
              </dt>
              <dd className="bg-line hidden h-1 w-8 overflow-hidden rounded-sm sm:block">
                <span
                  className="bg-chart-1 block h-full rounded-sm"
                  style={{ width: `${Math.min((share ?? 0) * 100, 100)}%` }}
                />
              </dd>
              <dd className="text-ink font-mono text-[10.5px] tabular-nums">
                {share === null ? "n/a" : `${Math.round(share * 100)}%`}
                <span className="sr-only"> ({label})</span>
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
