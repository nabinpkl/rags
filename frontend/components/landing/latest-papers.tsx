import Link from "next/link";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { LatestResponse } from "@/lib/api-client";

/** The newest papers the reader can actually open.
 *
 * D16 in list form: the API returns indexed papers only, so every row links
 * to the reader and none dead-ends. Rows carry what a reader scans for (title,
 * area, date, who); the arXiv id and reference count were bookkeeping.
 */
export function LatestPapers({ papers }: { papers: LatestResponse["papers"] }) {
  if (papers.length === 0) return null;

  return (
    <DashboardPanel title="Just indexed" bodyClassName="px-0 pb-0">
      <ol className="border-line divide-line flex-1 divide-y border-t">
        {papers.map((paper) => (
          <li key={paper.arxiv_id}>
            <Link
              href={`/demo?paper=${encodeURIComponent(paper.arxiv_id)}`}
              // The whole row is the target (touch has no hover to hunt
              // with), so the accessible name is pinned to the title rather
              // than left to concatenate every metadata field in the row.
              aria-label={paper.title}
              className="group hover:bg-panel-hover block px-4 py-3 transition-colors motion-reduce:transition-none"
            >
              <span className="text-ink block text-[13.5px] leading-snug font-medium group-hover:underline">
                {paper.title}
              </span>
              <span className="text-muted mt-1.5 flex min-w-0 items-center gap-2 text-[11.5px]">
                <span className="bg-teal-soft text-teal-ink shrink-0 rounded px-1 py-px font-mono text-[10.5px]">
                  {paper.primary_category ?? "uncategorized"}
                </span>
                <span className="shrink-0 tabular-nums">{formatDate(paper.published)}</span>
                {paper.authors && (
                  <span className="min-w-0 truncate" title={paper.authors}>
                    · {paper.authors}
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </DashboardPanel>
  );
}

/** "2026-09-03" to "3 Sep 2026": the catalog date is ISO, so this splits
 * strings instead of parsing dates. */
function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  const name = new Date(Date.UTC(Number(year), Number(month) - 1, 1)).toLocaleString("en-US", {
    month: "short",
    timeZone: "UTC",
  });
  return `${Number(day)} ${name} ${year}`;
}
