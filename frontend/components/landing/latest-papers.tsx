import {
  Bot,
  Brain,
  ChevronRight,
  Code2,
  Cpu,
  Eye,
  FileText,
  type LucideIcon,
  MessageSquareText,
  Network,
  Radio,
  Search,
  ShieldCheck,
  Sigma,
} from "lucide-react";
import Link from "next/link";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { LatestResponse } from "@/lib/api-client";

/** The glyph encodes the paper's FIELD, so the column can be scanned by shape
 * before it is read. Decorative-only icons would make the list slower to
 * read, not faster; an unmapped category falls back to the neutral document. */
const CATEGORY_ICON: Record<string, LucideIcon> = {
  "cs.CL": MessageSquareText,
  "cs.CV": Eye,
  "cs.LG": Brain,
  "cs.AI": Bot,
  "cs.RO": Cpu,
  "cs.IR": Search,
  "cs.CR": ShieldCheck,
  "cs.SE": Code2,
  "cs.NI": Network,
  "cs.DC": Network,
  "cs.IT": Radio,
  "stat.ML": Sigma,
  "math.OC": Sigma,
};

/** What just landed — the newest papers the reader can actually open.
 *
 * D16 in list form: the API returns indexed papers only, so every row links
 * to /app and none dead-ends. A paper posted yesterday is absent until the
 * index run covers it, which is the one thing here a reader cannot work out
 * by looking, so it is the one thing the header says.
 */
export function LatestPapers({ papers }: { papers: LatestResponse["papers"] }) {
  if (papers.length === 0) return null;

  return (
    <DashboardPanel
      icon={FileText}
      title="What just landed"
      meta={`${papers.length} newest`}
      description="This week's arrivals appear here once the index run covers them: freshness follows the corpus, not the clock."
    >
      {/* No `overflow-hidden`: it would clip the base-layer focus ring
          (globals.css) on the first and last rows, and that ring is not a
          component's to re-spell. The rows carry the container's corner
          radius themselves so a hovered end row still fills to the border. */}
      <ol className="border-line divide-line flex-1 divide-y rounded border [&>li:first-child>a]:rounded-t-[3px] [&>li:last-child>a]:rounded-b-[3px]">
        {papers.map((paper) => {
          const Icon = CATEGORY_ICON[paper.primary_category ?? ""] ?? FileText;
          return (
            <li key={paper.arxiv_id}>
              <Link
                href={`/app?paper=${encodeURIComponent(paper.arxiv_id)}`}
                // The whole row is the target (touch has no hover to hunt
                // with), so the accessible name is pinned to the title rather
                // than left to concatenate every metadata field in the row.
                aria-label={paper.title}
                className="group hover:bg-paper flex items-start gap-3 px-3.5 py-3 transition-colors motion-reduce:transition-none"
              >
                <span
                  className="bg-teal-soft text-teal-ink mt-px grid size-7 shrink-0 place-items-center rounded"
                  aria-hidden
                >
                  <Icon className="size-[14px]" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-ink block text-[13.5px] leading-snug font-medium group-hover:underline">
                    {paper.title}
                  </span>
                  <span className="text-muted mt-1.5 flex items-center gap-2 font-mono text-[10.5px]">
                    <span className="bg-teal-soft text-teal-ink shrink-0 rounded px-1 py-px">
                      {paper.primary_category ?? "uncategorized"}
                    </span>
                    <span className="truncate tabular-nums">
                      {paper.arxiv_id}
                      {paper.version ?? ""} · {formatDate(paper.published)}
                    </span>
                    <span className="ml-auto shrink-0 tabular-nums whitespace-nowrap">
                      {paper.ref_count === 1 ? "1 ref" : `${paper.ref_count} refs`}
                    </span>
                  </span>
                  {paper.authors && (
                    <span
                      className="text-muted mt-1 block truncate font-mono text-[10.5px]"
                      title={paper.authors}
                    >
                      {paper.authors}
                    </span>
                  )}
                </span>
                <ChevronRight
                  className="text-line group-hover:text-muted mt-1 size-4 shrink-0 transition-colors motion-reduce:transition-none"
                  aria-hidden
                />
              </Link>
            </li>
          );
        })}
      </ol>
    </DashboardPanel>
  );
}

/** "2026-09-03" to "3 Sep 2026" — the catalog date is ISO, so this splits
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
