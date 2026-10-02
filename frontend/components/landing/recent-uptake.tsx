import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { Foundation, UptakeResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** What one month's papers were already citing from the month before it.
 *
 * Measurable only across two COMPLETE months: uptake counted over a
 * half-collected month measures our download schedule. The API refuses
 * months below the coverage floor, and this panel renders nothing rather
 * than guessing when no two complete months adjoin.
 *
 * Each row carries both numbers: the big one is citations from the later
 * month (the finding), the small one the work's total, without which "37"
 * reads as the whole of a work's reception.
 */
export function RecentUptake({
  uptake,
  onSelect,
}: {
  uptake: UptakeResponse;
  onSelect: (foundation: Foundation) => void;
}) {
  if (!uptake.from_month || !uptake.to_month || uptake.works.length === 0) return null;
  const from = formatIdMonth(uptake.from_month, "long");
  const to = formatIdMonth(uptake.to_month, "long");
  const max = uptake.works[0]?.citations_from ?? 1;

  return (
    <DashboardPanel
      title="Cited within weeks"
      description={`${from} papers that ${to} papers already cite.`}
      bodyClassName="px-0 pb-0"
    >
      <ol className="border-line divide-line flex-1 divide-y border-t">
        {uptake.works.map(({ work, citations_from: citations }) => (
          <li key={work.arxiv_id}>
            <button
              type="button"
              onClick={() => onSelect(work)}
              className="group hover:bg-panel-hover flex w-full items-start gap-4 px-4 py-3 text-left transition-colors motion-reduce:transition-none"
            >
              <span className="min-w-0 flex-1">
                <span className="text-ink block text-[13.5px] leading-snug font-medium group-hover:underline">
                  {work.title ?? work.arxiv_id}
                </span>
                <span className="text-muted mt-1 block text-[11.5px] tabular-nums">
                  {[
                    work.primary_category_name ?? work.primary_category,
                    `${work.cited_by.toLocaleString()} in total`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
              <span className="w-20 shrink-0 pt-px">
                <span className="font-mono text-ink block text-right text-[15px] leading-none font-semibold tabular-nums">
                  {citations.toLocaleString()}
                </span>
                <span className="bg-line mt-1.5 block h-1.5 overflow-hidden rounded-sm">
                  <span
                    className="bg-chart-1 block h-full rounded-sm"
                    style={{ width: `${Math.max((citations / max) * 100, 4)}%` }}
                  />
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </DashboardPanel>
  );
}
