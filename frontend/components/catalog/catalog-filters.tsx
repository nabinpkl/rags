"use client";

import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { BrandMark } from "@/components/shell/brand-mark";
import type { CatalogBucket, CatalogFacetsResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";
import { cn } from "@/lib/utils";

const DEBOUNCE_MS = 300;

// Fields and months both have a long tail of one-paper buckets from an older
// facet sample. The rail lists the largest and keeps the rest one click away
// rather than dropping them: the API filters by any of them.
const ROWS_SHOWN = 10;

/** What we hold of a paper, as the three states the corpus actually has.
 * Every paper has a catalog row; some have extracted text; a few are chunked
 * and searchable. The labels say what the reader gets, not what our pipeline
 * calls the stage. */
export const HOLDINGS = [
  { value: "all", label: "Everything arXiv posted" },
  { value: "text", label: "We have the text" },
  { value: "indexed", label: "The agent can read it" },
] as const;

export const SORTS = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "cited", label: "Most cited" },
  { value: "relevance", label: "Best match" },
] as const;

export type Holding = (typeof HOLDINGS)[number]["value"];
export type Sort = (typeof SORTS)[number]["value"];

export type CatalogFilterState = {
  q: string;
  category: string | null;
  month: string | null;
  holding: Holding;
  sort: Sort;
};

export const EMPTY_FILTER: CatalogFilterState = {
  q: "",
  category: null,
  month: null,
  holding: "all",
  sort: "newest",
};

/** The catalog's rail: the query, in the order a reader builds one.
 *
 * Counted lists rather than wrapping chips. The corpus has 40 fields and 234
 * id-months; drawn as chips they were a wall the results sat below, and drawn
 * as rows with the count right-aligned they are scannable. The count is the
 * point — it says what picking this instead would give, which is why the API
 * drops a dimension's own filter before counting it.
 *
 * Same trim as the dashboard's rail (`dashboard-sidebar.tsx`): one brand
 * block, mono section labels, a bordered footer. Two rails that differed in
 * their trim would read as two products.
 */
export function CatalogFilters({
  state,
  facets,
  onChange,
}: {
  state: CatalogFilterState;
  facets: CatalogFacetsResponse | undefined;
  onChange: (next: Partial<CatalogFilterState>) => void;
}) {
  const holdings = new Map(facets?.holdings.map((bucket) => [bucket.value, bucket.papers]));
  const filtered = (Object.keys(EMPTY_FILTER) as (keyof CatalogFilterState)[]).some(
    (key) => state[key] !== EMPTY_FILTER[key],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="border-line flex h-[57px] shrink-0 items-center gap-2.5 border-b px-4">
        <BrandMark tagline="every paper we know of" />
      </div>

      {/* The last section drops its own rule: the footer already draws one,
          and two hairlines with a gap of empty rail between them read as a
          section that failed to load. */}
      <div className="min-h-0 flex-1 overflow-y-auto [&>section:last-child]:border-b-0">
        <div className="border-line border-b p-3">
          <SearchBox value={state.q} onCommit={(q) => onChange({ q })} />
        </div>

        <Section label="Show">
          {HOLDINGS.map((holding) => (
            <Row
              key={holding.value}
              active={state.holding === holding.value}
              resting={holding.value === EMPTY_FILTER.holding}
              count={holdings.get(holding.value)}
              onClick={() => onChange({ holding: holding.value })}
            >
              {holding.label}
            </Row>
          ))}
        </Section>

        <Section label="Order">
          <div className="grid grid-cols-2 gap-1">
            {SORTS.map((sort) => {
              const current = state.sort === sort.value;
              // Ranking by match needs something to match against, and the
              // API refuses the pair outright rather than reorder silently.
              const off = sort.value === "relevance" && state.q.trim() === "";
              return (
                <button
                  key={sort.value}
                  type="button"
                  disabled={off}
                  aria-pressed={current}
                  onClick={() => onChange({ sort: sort.value })}
                  className={cn(
                    "rounded px-2 py-1.5 text-left text-[13px] transition-colors motion-reduce:transition-none",
                    off && "text-line cursor-not-allowed",
                    !off &&
                      current &&
                      "bg-teal-soft text-teal-ink hover:bg-teal-soft-strong font-medium",
                    !off && !current && "text-ink hover:bg-paper",
                  )}
                >
                  {sort.label}
                </button>
              );
            })}
          </div>
        </Section>

        <BucketSection
          label="Field"
          buckets={facets?.categories}
          selected={state.category}
          format={(value) => value}
          onSelect={(category) => onChange({ category })}
        />
        <BucketSection
          label="Month posted"
          buckets={facets?.months}
          selected={state.month}
          format={(value) => formatIdMonth(value, "short")}
          onSelect={(month) => onChange({ month })}
        />
      </div>

      {filtered && (
        <div className="border-line shrink-0 border-t p-3">
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTER)}
            className="border-line text-ink hover:bg-paper w-full rounded border px-3 py-2 text-[13px] transition-colors motion-reduce:transition-none"
          >
            Clear the filter
          </button>
        </div>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="border-line border-b p-2">
      <h2 className="text-muted px-2 pt-1 pb-2 font-mono text-[10px] tracking-[0.14em] uppercase">
        {label}
      </h2>
      {children}
    </section>
  );
}

function BucketSection({
  label,
  buckets,
  selected,
  format,
  onSelect,
}: {
  label: string;
  buckets: CatalogBucket[] | undefined;
  selected: string | null;
  format: (value: string) => string;
  onSelect: (value: string | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!buckets || buckets.length === 0) return null;
  const head = buckets.slice(0, ROWS_SHOWN);
  const chosen = buckets.find((bucket) => bucket.value === selected);
  // A chosen value stays visible even when it ranks below the cut, or the
  // rail would look untouched while the results say otherwise.
  const shown = expanded ? buckets : chosen && !head.includes(chosen) ? [chosen, ...head] : head;
  const hidden = buckets.length - shown.length;

  return (
    <Section label={label}>
      <Row active={selected === null} resting onClick={() => onSelect(null)}>
        Any
      </Row>
      {shown.map((bucket) => (
        <Row
          key={bucket.value}
          active={selected === bucket.value}
          count={bucket.papers}
          mono
          onClick={() => onSelect(selected === bucket.value ? null : bucket.value)}
        >
          {format(bucket.value)}
        </Row>
      ))}
      {(hidden > 0 || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-muted hover:text-ink w-full rounded px-2 py-1.5 text-left text-[12px] underline underline-offset-2 transition-colors motion-reduce:transition-none"
        >
          {expanded ? "Show fewer" : `${hidden.toLocaleString()} more`}
        </button>
      )}
    </Section>
  );
}

/** One value and its count. The value is content and takes full ink; the
 * count is metadata bound to it, so it is muted. */
function Row({
  active,
  resting,
  count,
  mono,
  onClick,
  children,
}: {
  active: boolean;
  /** This value is the section's default, so being on it is not a choice the
   * reader made. It still reads as current, but it does not spend the accent:
   * teal in this rail means "you narrowed something". */
  resting?: boolean;
  count?: number;
  mono?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const accent = active && !resting;
  return (
    <button
      type="button"
      aria-pressed={active}
      // Spelled out rather than left to the two spans: a flex row has no text
      // node between them, so the computed name would run together as
      // "cs.CV12,430".
      aria-label={count === undefined ? undefined : `${children} ${count.toLocaleString()}`}
      onClick={onClick}
      className={cn(
        "flex w-full items-baseline gap-2 rounded px-2 py-1.5 text-left transition-colors motion-reduce:transition-none",
        // Both branches carry a hover: a selected row is still a target, and
        // it steps away from its resting surface rather than toward it.
        accent ? "bg-teal-soft text-teal-ink hover:bg-teal-soft-strong" : "text-ink hover:bg-paper",
      )}
    >
      <span
        className={cn(
          "min-w-0 flex-1 truncate",
          mono ? "font-mono text-[12px]" : "text-[13px]",
          active && "font-medium",
        )}
      >
        {children}
      </span>
      {count !== undefined && (
        <span
          className={cn(
            "shrink-0 font-mono text-[11.5px] tabular-nums",
            accent ? "text-teal-ink" : "text-muted",
          )}
        >
          {count.toLocaleString()}
        </span>
      )}
    </button>
  );
}

/** The text box owns its own keystrokes and commits on a pause: the URL is
 * the filter's home, and writing it per character would refetch per letter. */
function SearchBox({ value, onCommit }: { value: string; onCommit: (value: string) => void }) {
  const [text, setText] = useState(value);
  const [synced, setSynced] = useState(value);

  // An external change (a pasted link, Clear) resyncs the input during render
  // rather than in an effect, per the React docs' "adjusting state when a
  // prop changes".
  if (value !== synced) {
    setSynced(value);
    setText(value);
  }

  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => onCommit(text), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text, value, onCommit]);

  return (
    <div className="relative">
      <Search
        className="text-muted pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
        aria-hidden
      />
      <input
        type="search"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Title or abstract"
        aria-label="Search titles and abstracts"
        // 16px here: iOS Safari zooms the page when a focused input is under
        // 16px and does not undo the zoom on blur.
        className="border-line bg-paper text-ink placeholder:text-muted w-full rounded border py-2 pr-7 pl-8 text-[16px] outline-none md:text-[13px]"
      />
      {text !== "" && (
        <button
          type="button"
          onClick={() => setText("")}
          aria-label="Clear search"
          className="text-muted hover:text-ink absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-1 transition-colors motion-reduce:transition-none"
        >
          <X className="size-3" aria-hidden />
        </button>
      )}
    </div>
  );
}
