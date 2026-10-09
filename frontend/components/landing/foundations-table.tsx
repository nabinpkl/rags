"use client";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { Foundation } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** The ranking that survives a rerun.
 *
 * It is a count of parsed citations and nothing else: no clustering, no
 * theme labels. On this data two runs of the same clustering agree on only
 * 43-61% of pairs, so a named theme would be a claim about our code rather
 * than about the literature (see methods-note.tsx, which says so on the page).
 *
 * Rows carry title, area and when the work was posted. Author lists were
 * cut: on technical reports they ran to "+553" and said less than the title.
 */
export function FoundationsTable({
  foundations,
  onSelect,
}: {
  foundations: Foundation[];
  onSelect: (foundation: Foundation) => void;
}) {
  // The bar is scaled to the top row, not to the cohort: the leader takes
  // ~7% of the cohort, so a cohort-relative bar would render every row as an
  // indistinguishable sliver.
  const max = foundations[0]?.cited_by ?? 1;

  return (
    <DashboardPanel title="Most cited" bodyClassName="px-0 pb-0">
      {/* The ranking scrolls inside its panel rather than pushing the rest of
          the dashboard below the fold: 40 rows at full height is a page, not a
          panel, and the bands under it would never be seen. */}
      <div className="border-line max-h-[52vh] min-h-[280px] overflow-y-auto rounded-b-md border-t">
        <table className="w-full border-collapse tabular-nums">
          <thead className="bg-panel sticky top-0 z-10">
            <tr>
              {["", "Paper", "Area", "Cited by"].map((label, i) => (
                <th
                  key={label || i}
                  scope="col"
                  className={`border-line text-muted border-b px-3 py-2 text-[11px] font-medium ${i === 3 ? "text-right" : "text-left"} ${i === 2 ? "hidden sm:table-cell" : ""}`}
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
                className="hover:bg-panel-hover focus-visible:outline-teal cursor-pointer transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 motion-reduce:transition-none"
              >
                <td className="border-line text-muted w-10 border-b px-3 py-2.5 align-baseline font-mono text-[11.5px]">
                  {i + 1}
                </td>
                <td className="border-line border-b px-3 py-2.5 align-baseline">
                  <span className="font-serif text-ink block max-w-[56ch] text-[15px]">
                    {foundation.title ?? (
                      <span className="text-muted italic">
                        not in the catalog snapshot ({foundation.arxiv_id})
                      </span>
                    )}
                  </span>
                  <span className="text-muted mt-0.5 block text-[11.5px] tabular-nums">
                    <span className="sm:hidden">
                      {categoryLabel(foundation) && `${categoryLabel(foundation)} · `}
                    </span>
                    {posted(foundation)}
                  </span>
                </td>
                <td className="border-line text-ink-2 hidden border-b px-3 py-2.5 align-baseline text-[12.5px] sm:table-cell">
                  {categoryLabel(foundation)}
                </td>
                <td className="border-line border-b px-3 py-2.5 text-right align-baseline whitespace-nowrap sm:w-[176px]">
                  <span className="bg-line mr-2.5 hidden h-[7px] w-[100px] overflow-hidden rounded-sm align-middle sm:inline-block">
                    <span
                      className="bg-teal block h-full rounded-sm"
                      style={{ width: `${(foundation.cited_by / max) * 100}%` }}
                    />
                  </span>
                  <b className="text-ink inline-block w-[3.4em] text-right font-mono text-[13px] font-semibold">
                    {foundation.cited_by.toLocaleString()}
                  </b>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DashboardPanel>
  );
}

/** arXiv's name for the area, or the bare code outside cs, which the name
 * table does not cover. */
function categoryLabel(foundation: Foundation): string | null {
  return foundation.primary_category_name ?? foundation.primary_category;
}

/** When the work was first posted. A new-style id's YYMM prefix IS that
 * month; an old-style id (`cs/0112017`) has none, so the catalog year stands
 * in. */
function posted(foundation: Foundation): string {
  if (/^\d{4}\./.test(foundation.arxiv_id)) {
    return formatIdMonth(foundation.arxiv_id.slice(0, 4), "short");
  }
  return foundation.year ? String(foundation.year) : "";
}
