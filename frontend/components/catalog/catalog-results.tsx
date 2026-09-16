"use client";

import { ArrowUpRight, BookOpen } from "lucide-react";
import Link from "next/link";

import type { CatalogFilterState } from "@/components/catalog/catalog-filters";
import type { CatalogPaper } from "@/lib/api-client";
import { CATEGORY_ICON, UNMAPPED_CATEGORY_ICON } from "@/lib/category-icon";
import { formatIdMonth } from "@/lib/id-month";

/** Where a row can send the reader, which is the one thing that differs
 * between a paper we indexed and a paper we only know about.
 *
 * §6b: we never serve or proxy a PDF, so an unindexed row hands the reader
 * off to arxiv.org, and always at the version we recorded — an unpinned link
 * would resolve to whatever the paper becomes later, which is not the paper
 * this row counted.
 */
function destination(paper: CatalogPaper): { href: string; label: string; external: boolean } {
  if (paper.indexed) {
    return {
      href: `/app?paper=${encodeURIComponent(paper.arxiv_id)}`,
      label: "Open in the reader",
      external: false,
    };
  }
  const pinned = paper.version ? `${paper.arxiv_id}${paper.version}` : paper.arxiv_id;
  return { href: `https://arxiv.org/abs/${pinned}`, label: "Open on arXiv", external: true };
}

/** The filter, said back in words. A reader who changed three things in the
 * rail confirms the query here rather than re-reading three lists. */
function describe(state: CatalogFilterState): string {
  const parts = [
    state.holding === "indexed" ? "Papers the agent can read" : "Papers",
    state.category,
    state.month ? `posted ${formatIdMonth(state.month)}` : null,
    state.q.trim() ? `matching “${state.q.trim()}”` : null,
    state.holding === "text" ? "whose text we hold" : null,
  ].filter(Boolean);
  return parts.join(" · ");
}

/** The results, as one card per paper.
 *
 * No panel wraps them. A panel frame says "these things are one object read
 * together", which is true of the dashboard's charts and false of a list
 * whose length is a filter result: the reader takes one paper at a time, and
 * a card each is what makes each one its own target. The heading above is
 * therefore a page heading, not a panel header.
 */
export function CatalogResults({
  papers,
  total,
  state,
  loading,
  onLoadMore,
}: {
  papers: CatalogPaper[];
  total: number;
  state: CatalogFilterState;
  loading: boolean;
  onLoadMore: (() => void) | null;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="font-serif text-ink min-w-0 text-[18px] leading-tight font-semibold text-balance">
          {describe(state)}
        </h1>
        <p className="text-muted shrink-0 font-mono text-[11px] tracking-[0.08em] tabular-nums uppercase">
          {loading && papers.length === 0 ? "counting" : `${total.toLocaleString()} found`}
        </p>
      </div>

      {papers.length === 0 ? (
        loading ? (
          <SkeletonCards />
        ) : (
          <p className="border-line text-ink-2 rounded-md border border-dashed px-4 py-16 text-center text-[13.5px]">
            Nothing in the catalog matches that. Widen the field or the month, or drop a word from
            the search.
          </p>
        )
      ) : (
        <>
          <ol className="flex flex-col gap-2.5">
            {papers.map((paper) => (
              <li key={paper.arxiv_id}>
                <PaperCard paper={paper} />
              </li>
            ))}
          </ol>
          {onLoadMore && (
            <button
              type="button"
              onClick={onLoadMore}
              disabled={loading}
              className="border-line bg-panel text-ink hover:bg-paper disabled:text-muted mt-1 rounded-md border px-4 py-2.5 text-[13px] transition-colors disabled:cursor-wait motion-reduce:transition-none"
            >
              {loading
                ? "Loading…"
                : `Show more (${(total - papers.length).toLocaleString()} left)`}
            </button>
          )}
        </>
      )}
    </div>
  );
}

function PaperCard({ paper }: { paper: CatalogPaper }) {
  const { href, label, external } = destination(paper);
  const Icon = CATEGORY_ICON[paper.primary_category ?? ""] ?? UNMAPPED_CATEGORY_ICON;
  const Destination = external ? ArrowUpRight : BookOpen;

  return (
    <Link
      href={href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      // The whole row is the target — touch has no hover to hunt with — so
      // the accessible name is pinned to the title and the destination,
      // rather than left to concatenate every metadata field in the row.
      aria-label={`${paper.title} — ${label}`}
      className="group border-line bg-panel hover:border-teal-ink/40 hover:bg-paper flex items-start gap-3.5 rounded-md border px-4 py-4 transition-colors motion-reduce:transition-none"
    >
      {/* Neutral, unlike the dashboard's six-row version of this list: thirty
          teal tiles down a column read as a stripe and pull rank from the
          titles. The category chip below still carries the accent, so the
          field is named once in colour and once in shape. */}
      <span
        className="bg-paper text-muted group-hover:bg-teal-soft group-hover:text-teal-ink mt-0.5 grid size-7 shrink-0 place-items-center rounded transition-colors motion-reduce:transition-none"
        aria-hidden
      >
        <Icon className="size-[14px]" />
      </span>

      <span className="min-w-0 flex-1">
        <span className="text-ink block text-[15.5px] leading-[1.35] font-semibold group-hover:underline">
          {paper.title}
        </span>
        {paper.authors && (
          <span className="text-muted mt-1.5 block truncate font-mono text-[12px]">
            {paper.authors}
          </span>
        )}
        {/* The one block of running prose on this page, so it takes the
            middle ink tier rather than the metadata grey, and a measure that
            stops near 76 characters. No `block`: `line-clamp` works by
            setting display to -webkit-box, and a display utility after it
            wins and silently un-clamps the abstract. */}
        <span className="text-ink-2 mt-2 line-clamp-3 max-w-[76ch] text-[13.5px] leading-[1.6]">
          {paper.abstract}
        </span>
        <span className="text-muted mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[11.5px]">
          <span className="bg-teal-soft text-teal-ink shrink-0 rounded px-1.5 py-0.5">
            {paper.primary_category}
          </span>
          <span className="tabular-nums">
            {paper.arxiv_id}
            {paper.version ?? ""} · {formatDate(paper.published)}
          </span>
          {paper.cited_by > 0 && (
            <span className="tabular-nums">cited by {paper.cited_by.toLocaleString()} here</span>
          )}
        </span>
      </span>

      {/* The glyph is the whole affordance: an arrow leaving the box means
          the row leaves the site, a book means it opens in our reader. The
          words are in the row's accessible name, not repeated 30 times down
          the column as a bordered button. */}
      <Destination
        className="text-muted group-hover:text-teal-ink mt-1 size-4 shrink-0 transition-colors motion-reduce:transition-none"
        aria-hidden
      />
    </Link>
  );
}

/** Cards at rest, so a slow first page reads as a list arriving rather than
 * a canvas that failed. Widths vary per card: five identical bars read as a
 * graphic, not as text loading. */
function SkeletonCards() {
  const widths = ["w-[62%]", "w-[45%]", "w-[71%]", "w-[54%]", "w-[66%]"];
  return (
    <ol className="flex flex-col gap-2.5" aria-hidden>
      {widths.map((width) => (
        <li
          key={width}
          className="border-line bg-panel flex items-start gap-3.5 rounded-md border px-4 py-4"
        >
          <span className="bg-line/40 mt-0.5 size-7 shrink-0 rounded" />
          <span className="min-w-0 flex-1">
            <span className={`bg-line/40 block h-4 rounded ${width}`} />
            <span className="bg-line/25 mt-2.5 block h-2.5 w-[30%] rounded" />
            <span className="bg-line/25 mt-2.5 block h-2.5 w-[88%] rounded" />
          </span>
        </li>
      ))}
    </ol>
  );
}

/** "2026-09-03" to "3 Sep 2026". The catalog date is ISO, so this splits the
 * string rather than parsing it into a local-timezone Date. */
function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  const name = new Date(Date.UTC(Number(year), Number(month) - 1, 1)).toLocaleString("en-US", {
    month: "short",
    timeZone: "UTC",
  });
  return `${Number(day)} ${name} ${year}`;
}
