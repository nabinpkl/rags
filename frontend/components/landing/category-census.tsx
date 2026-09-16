import { PieChart } from "lucide-react";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { CategoryCensusResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** Every other panel on this page counts what WE hold. This one counts what
 * arXiv posted, which is a different claim and only survives on a month we
 * hold whole: July and August 2026 at 99.95% and 99.99%. A month below the
 * coverage floor is named in the footer instead of drawn, because a missing
 * bar in a chart of the field's output reads as a field that stopped
 * publishing, when what stopped was our collecting.
 *
 * The categories are ranked once over the whole census and every month
 * answers for the same list in the same order, so the reader compares like
 * with like across months rather than across two different top-eights.
 */
export function CategoryCensus({ census }: { census: CategoryCensusResponse }) {
  if (census.months.length === 0) return null;
  // One scale across every bar in the table: per-row scaling would draw a
  // 2% category the same width as an 18% one.
  const peak = Math.max(
    ...census.months.flatMap((month) =>
      month.categories.map((share) => share.papers / Math.max(month.papers, 1)),
    ),
    0.01,
  );

  return (
    <DashboardPanel
      icon={PieChart}
      title="What the field posted"
      meta={census.months.map((month) => formatIdMonth(month.month, "short")).join(" · ")}
      description="Primary category of every cs paper arXiv announced in these months. Not our sample of them: we hold effectively all of both, so this is the census."
      footer={<CensusFooter census={census} />}
    >
      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-[12.5px]">
          <thead>
            <tr className="text-muted font-mono text-[10px] tracking-[0.1em] uppercase">
              <th className="py-1 text-left font-normal">Category</th>
              {census.months.map((month) => (
                <th key={month.month} className="py-1 pl-4 text-right font-normal">
                  {formatIdMonth(month.month, "short")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {census.categories.map((category, row) => (
              <tr key={category}>
                <th scope="row" className="text-ink py-1 pr-3 text-left font-normal">
                  <span className="font-mono text-[11.5px]">{category}</span>
                </th>
                {census.months.map((month) => {
                  const share = month.categories[row]?.papers ?? 0;
                  const fraction = share / Math.max(month.papers, 1);
                  return (
                    <td key={month.month} className="py-1 pl-4">
                      <span className="flex items-center justify-end gap-2">
                        <span className="bg-paper hidden h-1.5 w-full max-w-[120px] overflow-hidden rounded-sm sm:block">
                          <span
                            className="bg-chart-1 block h-full rounded-sm"
                            style={{ width: `${(fraction / peak) * 100}%` }}
                          />
                        </span>
                        <span className="text-ink w-11 shrink-0 text-right font-mono tabular-nums">
                          {(fraction * 100).toFixed(1)}%
                        </span>
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DashboardPanel>
  );
}

/** The denominators, and the month that could not be drawn. Both are things a
 * reader cannot recover from the bars. */
function CensusFooter({ census }: { census: CategoryCensusResponse }) {
  const counts = census.months
    .map(
      (month) =>
        `${formatIdMonth(month.month, "short")} ${month.papers.toLocaleString()} of ${month.catalog_papers.toLocaleString()}`,
    )
    .join("; ");
  const excluded = census.excluded
    .map((month) => {
      const held = month.papers_held.toLocaleString();
      if (!month.catalog_papers) return `${formatIdMonth(month.month)} (${held} papers held)`;
      const share = Math.round((month.papers_held / month.catalog_papers) * 100);
      return `${formatIdMonth(month.month)}, where we hold ${share}% of the ${month.catalog_papers.toLocaleString()} papers arXiv posted`;
    })
    .join("; ");

  return (
    <>
      Papers held against the catalog: {counts}. Each paper counts once, under the primary category
      arXiv filed it in.
      {excluded && ` Left out: ${excluded} — too little of it to speak for the month.`}
    </>
  );
}
