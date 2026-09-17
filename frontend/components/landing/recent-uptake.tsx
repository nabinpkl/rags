import { Zap } from "lucide-react";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { Foundation, UptakeResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** What one month's papers were already citing from the month before it.
 *
 * The panel exists because two COMPLETE months make it measurable. Uptake
 * counted over a half-collected month measures our download schedule: a work
 * looks unused when what is missing is the papers that cite it. The API
 * refuses months below the coverage floor for that reason, and this panel
 * shows nothing rather than guessing when no two complete months adjoin.
 *
 * Each row carries both numbers. The big one is the citations from the later
 * month, which is the finding; the small one is the work's total in the
 * corpus, without which "37" reads as the whole of a work's reception.
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
      icon={Zap}
      title="Cited within weeks"
      meta={`${to} citing ${from}`}
      description={`Work posted in ${from} that ${to} papers were already building on. Both months are held in full, so a low count here means little uptake rather than little collecting.`}
      footer={`${uptake.works_total.toLocaleString()} ${from} papers drew ${uptake.edges_total.toLocaleString()} citations from ${to} papers, inside a window of one to eight weeks.`}
    >
      <ol className="border-line divide-line flex-1 divide-y rounded border">
        {uptake.works.map(({ work, citations_from: citations }) => (
          <li key={work.arxiv_id}>
            <button
              type="button"
              onClick={() => onSelect(work)}
              className="group hover:bg-panel-hover flex w-full items-start gap-3 px-3.5 py-2.5 text-left transition-colors motion-reduce:transition-none"
            >
              <span className="min-w-0 flex-1">
                <span className="text-ink block text-[13.5px] leading-snug font-medium group-hover:underline">
                  {work.title ?? work.arxiv_id}
                </span>
                <span className="text-muted mt-1.5 flex items-center gap-2 font-mono text-[10.5px]">
                  <span className="bg-teal-soft text-teal-ink shrink-0 rounded px-1 py-px">
                    {work.primary_category ?? "uncategorized"}
                  </span>
                  <span className="truncate tabular-nums">
                    {work.arxiv_id}
                    {work.version ?? ""} · {work.cited_by.toLocaleString()} citations in all
                  </span>
                </span>
              </span>
              <span className="w-24 shrink-0 pt-px">
                <span className="font-mono text-ink block text-right text-[15px] leading-none font-semibold tabular-nums">
                  {citations.toLocaleString()}
                </span>
                {/* The bar is the comparison the eye makes first; the number
                    beside it is what the reader quotes. */}
                <span className="bg-paper mt-1.5 block h-1.5 overflow-hidden rounded-sm">
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
