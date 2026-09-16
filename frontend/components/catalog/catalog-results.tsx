"use client";

import { ArrowUpRight, BookOpen, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { type RefObject, useRef } from "react";

import type { CatalogFilterState } from "@/components/catalog/catalog-filters";
import { type NextPage, useInfiniteVirtualList } from "@/hooks/use-infinite-virtual-list";
import type { CatalogPaper } from "@/lib/api-client";
import { CATEGORY_ICON, UNMAPPED_CATEGORY_ICON } from "@/lib/category-icon";
import { formatIdMonth } from "@/lib/id-month";
import { licenseOf } from "@/lib/license-label";

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
 * rail confirms them here rather than re-reading three selects.
 *
 * The search text is deliberately absent: it sits in the field one line
 * above, in the reader's own spelling, so repeating it here would be the page
 * reading its own input back. */
function describe(state: CatalogFilterState): string {
  const parts = [
    state.holding === "indexed" ? "Papers the agent can read" : "Papers",
    state.category,
    state.month ? `posted ${formatIdMonth(state.month)}` : null,
    state.holding === "text" ? "whose text we hold" : null,
  ].filter(Boolean);
  return parts.join(" · ");
}

// A card at the widest tile: 120px image plus 32px padding and a border.
// Only the first layout uses it; every card is measured once it mounts.
const CARD_ESTIMATE_PX = 160;
// Cards are tall, so a few either side is a full screen of slack.
const OVERSCAN = 4;
// The API pages 30 at a time; asking 10 cards early leaves the next page
// most of a screen to arrive before the reader reaches the end.
const FETCH_AHEAD = 10;
// Matches the list's former `gap-2.5`.
const CARD_GAP_PX = 10;

/** The results, as one card per paper.
 *
 * No panel wraps them. A panel frame says "these things are one object read
 * together", which is true of the dashboard's charts and false of a list
 * whose length is a filter result: the reader takes one paper at a time, and
 * a card each is what makes each one its own target. The heading above is
 * therefore a page heading, not a panel header.
 *
 * The list is windowed and pages itself in as the reader nears the end, the
 * same machinery as the /app explorer (`use-infinite-virtual-list.ts`). The
 * scroller is the page canvas, not a box of the list's own: the heading and
 * the search scroll away with the cards, so the list has to be told where in
 * that canvas it starts.
 */
export function CatalogResults({
  papers,
  total,
  state,
  loading,
  page,
  scrollElement,
}: {
  papers: CatalogPaper[];
  total: number;
  state: CatalogFilterState;
  loading: boolean;
  page: NextPage;
  scrollElement: HTMLElement | null;
}) {
  // Here rather than in the list: the list unmounts while a new filter's
  // first page loads, and the reset to the top has to happen then, not once
  // the rows are back and the reader has been looking at a skeleton 14,000px
  // down the canvas.
  const listRef = useRef<HTMLOListElement>(null);
  const windowed = useInfiniteVirtualList({
    count: papers.length,
    scrollElement,
    listRef,
    estimateSize: CARD_ESTIMATE_PX,
    overscan: OVERSCAN,
    gap: CARD_GAP_PX,
    fetchAhead: FETCH_AHEAD,
    page,
    // The filter, not the loaded rows: a new page arriving is the same list,
    // a new filter is a different one.
    resetKey: JSON.stringify(state),
    rememberAs: "catalog",
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="font-serif text-ink min-w-0 text-[22px] leading-[1.2] font-semibold text-balance">
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
        <PaperList
          papers={papers}
          total={total}
          page={page}
          listRef={listRef}
          windowed={windowed}
        />
      )}
    </div>
  );
}

function PaperList({
  papers,
  total,
  page,
  listRef,
  windowed: { virtualizer, items, scrollMargin },
}: {
  papers: CatalogPaper[];
  total: number;
  page: NextPage;
  listRef: RefObject<HTMLOListElement | null>;
  windowed: ReturnType<typeof useInfiniteVirtualList>;
}) {
  return (
    <>
      {/* The tile sizes off THIS width, not the viewport's: a docked rail
          takes 264px, so a 1024px window leaves the list narrower than a
          600px one with the rail closed. Container queries decide layout
          inside a region (.claude/rules/frontend.md).

          Most cards are not in the DOM, so each one that is says where it
          sits in the whole result: a screen reader otherwise announces "list,
          7 items" for a result of 65,503. */}
      <ol
        ref={listRef}
        className="@container relative"
        style={{ height: virtualizer.getTotalSize() }}
      >
        {items.map((item) => {
          const paper = papers[item.index];
          return (
            <li
              key={paper.arxiv_id}
              data-index={item.index}
              ref={virtualizer.measureElement}
              aria-setsize={total}
              aria-posinset={item.index + 1}
              className="absolute inset-x-0 top-0"
              style={{ transform: `translateY(${item.start - scrollMargin}px)` }}
            >
              <PaperCard paper={paper} />
            </li>
          );
        })}
      </ol>
      <ListEnd shown={papers.length} total={total} page={page} />
    </>
  );
}

/** What is under the last loaded card: more arriving, a page that failed,
 * or the end.
 *
 * A failed page stops the list asking (the hook will not re-request it on
 * its own), so the retry here is the only way on, and it has to be a button
 * rather than a hope that scrolling again works. */
function ListEnd({ shown, total, page }: { shown: number; total: number; page: NextPage }) {
  if (page.isFetchNextPageError) {
    return (
      <div
        role="alert"
        className="border-line text-ink-2 flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed px-4 py-3 text-[13.5px]"
      >
        <span>
          The papers after {shown.toLocaleString()} of {total.toLocaleString()} did not load.
        </span>
        <button
          type="button"
          onClick={() => void page.fetchNextPage()}
          className="border-line bg-panel text-ink hover:bg-paper rounded-md border px-3 py-1.5 text-[13px] transition-colors motion-reduce:transition-none"
        >
          Try again
        </button>
      </div>
    );
  }
  return (
    <p
      aria-live="polite"
      className="text-muted py-2 text-center font-mono text-[11px] tracking-[0.08em] tabular-nums uppercase"
    >
      {page.isFetchingNextPage
        ? "Loading more"
        : page.hasNextPage
          ? `${shown.toLocaleString()} of ${total.toLocaleString()}`
          : `All ${total.toLocaleString()} shown`}
    </p>
  );
}

/** The card's left tile: a crop of the paper over its category glyph.
 *
 * The URL is derived from the id and asked for unconditionally, because the
 * server renders the crop on the first request for it and serves a file
 * every time after (D19). Nothing on the wire says whether a given paper has
 * an image yet, and nothing should: a field like that would go stale the
 * moment the renderer caught up, and it would need a corpus rebuild to
 * un-stale.
 *
 * `loading="lazy"` is doing real work here rather than saving bytes. Thirty
 * cards asking at once is thirty PDF renders on a cold cache, so the browser
 * asking only for what is near the viewport is what keeps the first screen
 * fast, and it is the same reason nothing here prefetches.
 *
 * The glyph underneath is the resting state, not a placeholder to swap: a
 * paper with no PDF 404s and the image hides itself, leaving the glyph. The
 * tile keeps its size either way — a gutter that changes width per row makes
 * a column of cards read as ragged.
 *
 * 4:3, because both sources are landscape — a figure as it sits on the page,
 * or the top half of page one. Cropped square, a title block would lose a
 * third of its width off each side.
 *
 * It grows to 160x120 where the card is wide enough, and stops there for two
 * reasons that happen to agree. 120px is the shortest card's inner height
 * (measured 2026-09-16: 131px), so a taller tile would start setting card
 * height instead of the text. And the JPEG is rendered 320px wide, so 160
 * CSS px is exactly 2x — past that the image upscales, and re-rendering it
 * larger is the knob D19 calls compliance-adjacent, not a layout tweak.
 *
 * It does NOT grow on a phone, where the text column is already down to
 * 200px and titles wrap to five lines. Vertical room is not the constraint
 * there; horizontal room is, and there is none.
 */
function Tile({ paper, Icon }: { paper: CatalogPaper; Icon: LucideIcon }) {
  return (
    <span
      className="bg-paper text-muted group-hover:bg-teal-soft group-hover:text-teal-ink relative mt-0.5 grid h-[60px] w-20 shrink-0 place-items-center overflow-hidden rounded @xl:h-[90px] @xl:w-[120px] @3xl:h-[120px] @3xl:w-40 transition-colors motion-reduce:transition-none"
      aria-hidden
    >
      {/* Grows with the tile, or a 160px box holds an 18px glyph adrift in
          it — the resting state has to look composed, not empty. */}
      <Icon className="size-[18px] @xl:size-6 @3xl:size-7" />
      {/* next/image optimizes nothing here: the export target runs no image
          server (images.unoptimized, D13) and the file is rendered at the one
          size this tile uses. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`/thumbs/${paper.arxiv_id}.jpg`}
        alt=""
        loading="lazy"
        decoding="async"
        // We hold a PDF for every paper in the catalog today, but a 404 is a
        // normal answer, not an error: hiding the element uncovers the glyph
        // beneath it, which beats a broken-image icon in thirty rows.
        onError={(event) => {
          event.currentTarget.hidden = true;
        }}
        className="absolute inset-0 size-full object-cover"
      />
    </span>
  );
}

/** One paper.
 *
 * The whole card is the target — touch has no hover to hunt with — but the
 * anchor is the TITLE, stretched over the card by a full-bleed pseudo
 * element. A card-wide `<a>` cannot contain the licence link, and the
 * licence link is not optional: showing a crop of a CC paper is conditional
 * on naming and linking its licence (D19).
 */
function PaperCard({ paper }: { paper: CatalogPaper }) {
  const { href, label, external } = destination(paper);
  const Icon = CATEGORY_ICON[paper.primary_category ?? ""] ?? UNMAPPED_CATEGORY_ICON;
  const Destination = external ? ArrowUpRight : BookOpen;
  const license = licenseOf(paper.license);

  return (
    <article className="group border-line bg-panel hover:border-teal-ink/40 hover:bg-paper relative flex items-start gap-3.5 rounded-md border px-4 py-4 transition-colors motion-reduce:transition-none">
      <Tile paper={paper} Icon={Icon} />

      <div className="min-w-0 flex-1">
        <h3 className="text-ink text-[18px] leading-[1.3] font-semibold @xl:text-[20px]">
          <Link
            href={href}
            {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
            // The name is pinned to the title and the destination rather than
            // left to concatenate every metadata field in the card.
            aria-label={`${paper.title} — ${label}`}
            className="after:absolute after:inset-0 hover:underline"
          >
            {paper.title}
          </Link>
        </h3>
        {paper.authors && (
          <span className="text-muted mt-1.5 block truncate font-mono text-[12px]">
            {paper.authors}
          </span>
        )}
        {/* The one block of running prose on this page, so it takes the
            middle ink tier rather than the metadata grey, and a measure that
            stops near 76 characters. Two lines: the abstract is here to say
            whether the title is worth opening, and a third line pushes the
            next paper's title off a phone screen without answering that any
            better. No `block`: `line-clamp` works by setting display to
            -webkit-box, and a display utility after it wins and silently
            un-clamps the abstract. */}
        <span className="text-ink-2 mt-2 line-clamp-2 max-w-[76ch] text-[13.5px] leading-[1.6]">
          {paper.abstract}
        </span>
        <span className="text-muted mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[11.5px]">
          <span className="bg-teal-soft text-teal-ink shrink-0 rounded px-1.5 py-0.5">
            {paper.primary_category}
          </span>
          <span className="tabular-nums">{formatDate(paper.published)}</span>
          {paper.cited_by > 0 && (
            <span className="tabular-nums">cited by {paper.cited_by.toLocaleString()} here</span>
          )}
          {license && (
            // Above the stretched title link, so it is reachable as its own
            // target. This is the licence notice the crop above is granted
            // on, not a metadata garnish.
            <a
              href={license.href}
              target="_blank"
              rel="license noopener noreferrer"
              className="hover:text-ink relative underline underline-offset-2"
            >
              {license.name}
            </a>
          )}
        </span>
      </div>

      {/* The glyph is the whole affordance: an arrow leaving the box means
          the card leaves the site, a book means it opens in our reader. The
          words are in the card's accessible name, not repeated 30 times down
          the column as a bordered button. */}
      <Destination
        className="text-muted group-hover:text-teal-ink mt-1 size-4 shrink-0 transition-colors motion-reduce:transition-none"
        aria-hidden
      />
    </article>
  );
}

/** Cards at rest, so a slow first page reads as a list arriving rather than
 * a canvas that failed. Widths vary per card: five identical bars read as a
 * graphic, not as text loading. */
function SkeletonCards() {
  const widths = ["w-[62%]", "w-[45%]", "w-[71%]", "w-[54%]", "w-[66%]"];
  return (
    // Same container as the real list, so the skeleton tile is the size the
    // arriving one will be and the row does not resize under the reader.
    <ol className="@container flex flex-col gap-2.5" aria-hidden>
      {widths.map((width) => (
        <li
          key={width}
          className="border-line bg-panel flex items-start gap-3.5 rounded-md border px-4 py-4"
        >
          <span className="bg-line/40 mt-0.5 h-[60px] w-20 shrink-0 rounded @xl:h-[90px] @xl:w-[120px] @3xl:h-[120px] @3xl:w-40" />
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
