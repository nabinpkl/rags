"use client";

import type { Foundation, LandingResponse } from "@/lib/api-client";

/** The ranking that survives a rerun.
 *
 * It is a count of parsed citations and nothing else — no clustering, no
 * theme labels. On this data two runs of the same clustering agree on only
 * 43-61% of pairs, so a named theme would be a claim about our code rather
 * than about the literature (see methods-note.tsx, which says so on the page).
 *
 * Author lists arrive already trimmed (`config.landing_max_authors`) — the
 * catalog's untrimmed lists were 94% of the payload, so they are cut where
 * that cost is paid, not here.
 */
export function FoundationsTable({
  stats,
  foundations,
  onSelect,
}: {
  stats: LandingResponse["stats"];
  foundations: Foundation[];
  onSelect: (foundation: Foundation) => void;
}) {
  // The bar is scaled to the top row, not to the cohort: the leader takes
  // ~7% of the cohort, so a cohort-relative bar would render every row as an
  // indistinguishable sliver.
  const max = foundations[0]?.cited_by ?? 1;

  return (
    <section id="ranking" className="mx-auto max-w-5xl scroll-mt-16 px-6 py-8">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-3.5 gap-y-1">
        <h2 className="font-serif text-ink text-2xl font-semibold">The foundations</h2>
        <span className="text-muted font-mono text-[11.5px]">
          ranked by how many of {stats.papers_with_references.toLocaleString()} recent papers cite
          them
        </span>
      </div>
      <p className="text-muted mb-4 max-w-[70ch] text-sm">
        This is the ranking that survives a rerun. It is a count of parsed citations — add a month
        of papers and the numbers move because the literature moved, not because an algorithm
        re-drew a boundary.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse tabular-nums">
          <thead>
            <tr>
              {["", "Work being built on", "Area", "Cited by"].map((label, i) => (
                <th
                  key={label || i}
                  scope="col"
                  className={`border-ink text-muted border-b-[1.5px] px-2.5 py-2 font-mono text-[10.5px] font-semibold tracking-[0.1em] uppercase ${i === 3 ? "text-right" : "text-left"}`}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {foundations.map((foundation, i) => (
              <tr
                key={foundation.arxiv_id}
                tabIndex={0}
                onClick={() => onSelect(foundation)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(foundation);
                  }
                }}
                className="hover:bg-panel focus-visible:outline-teal cursor-pointer focus-visible:outline-2 focus-visible:-outline-offset-2"
              >
                <td className="border-line text-muted w-10 border-b px-2.5 py-2.5 align-baseline font-mono text-[11.5px]">
                  {i + 1}
                </td>
                <td className="border-line border-b px-2.5 py-2.5 align-baseline">
                  <span className="font-serif text-ink block max-w-[56ch] text-[15.5px]">
                    {foundation.title ?? (
                      <span className="text-muted italic">
                        not in the catalog snapshot ({foundation.arxiv_id})
                      </span>
                    )}
                  </span>
                  <span className="text-muted mt-0.5 block text-[11.5px]">
                    {foundation.authors}
                    {foundation.year ? ` · ${foundation.year}` : ""}
                  </span>
                </td>
                <td className="border-line border-b px-2.5 py-2.5 align-baseline">
                  {foundation.primary_category && (
                    <span className="bg-teal-soft text-teal-ink rounded-[3px] px-1.5 py-0.5 font-mono text-[10.5px]">
                      {foundation.primary_category}
                    </span>
                  )}
                </td>
                <td className="border-line w-[180px] border-b px-2.5 py-2.5 text-right align-baseline whitespace-nowrap">
                  <span className="bg-line mr-2.5 hidden h-[7px] w-[104px] overflow-hidden rounded-sm align-middle sm:inline-block">
                    <span
                      className="bg-teal block h-full rounded-sm"
                      style={{ width: `${(foundation.cited_by / max) * 100}%` }}
                    />
                  </span>
                  <b className="text-ink inline-block w-[3.4em] text-right font-mono text-[13px] font-semibold">
                    {foundation.cited_by}
                  </b>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-muted mt-3.5 font-mono text-[11.5px]">
        Showing the top {foundations.length} of {stats.cited_works.toLocaleString()} cited works.
      </p>
    </section>
  );
}
