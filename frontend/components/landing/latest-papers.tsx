import Link from "next/link";

import type { LatestResponse } from "@/lib/api-client";

/** What just landed — the newest papers the reader can actually open.
//
// D16 in list form: the API only returns indexed papers, so every row links
// to /app and none dead-ends. A paper posted yesterday is absent until the
// index run covers it; the note below says exactly that, instead of letting
// the list read as "everything new". */
export function LatestPapers({ papers }: { papers: LatestResponse["papers"] }) {
  if (papers.length === 0) return null;

  return (
    <div id="latest" className="bg-panel border-line scroll-mt-20 rounded border p-5">
      <h2 className="font-serif text-ink mb-1 text-xl font-semibold">What just landed</h2>
      <p className="text-muted mb-4 max-w-[70ch] text-sm">
        The newest papers we hold and have indexed. This week&apos;s arrivals appear here once
        the index run covers them — freshness follows the corpus, not the clock.
      </p>
      <ol className="border-line divide-line divide-y rounded border">
        {papers.map((paper) => (
          <li key={paper.arxiv_id} className="px-4 py-3">
            <Link
              href={`/app?paper=${encodeURIComponent(paper.arxiv_id)}`}
              className="text-ink text-[14px] font-medium hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              {paper.title}
            </Link>
            <p className="text-muted mt-0.5 font-mono text-[11px]">
              {paper.arxiv_id}
              {paper.version ? paper.version : ""} · {formatDate(paper.published)} ·{" "}
              {paper.primary_category ?? "uncategorized"} ·{" "}
              {paper.ref_count === 1 ? "1 reference" : `${paper.ref_count} references`}
            </p>
            {paper.authors && (
              <p className="text-muted mt-0.5 truncate font-mono text-[11px]" title={paper.authors}>
                {paper.authors}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
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
