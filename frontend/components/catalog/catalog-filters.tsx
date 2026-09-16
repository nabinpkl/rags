"use client";

import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { BrandMark } from "@/components/shell/brand-mark";
import type { CatalogBucket, CatalogFacetsResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";
import { cn } from "@/lib/utils";

const DEBOUNCE_MS = 300;

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
 * Four selects rather than four lists of rows. The corpus has 40 fields and
 * 234 id-months, which as rows was a rail the reader scrolled past to reach
 * the next control, with the long tail parked behind a "224 more" expander
 * that existed only because a flat list could not hold them. A select holds
 * all 234, so every month is one control away, and the whole query fits
 * above the fold with no scrolling at all.
 *
 * Native `<select>`, not a built menu: the rail's own scroll container
 * clips an absolutely-positioned popup, and the platform's list already
 * handles placement, keyboard, type-ahead and 234 options. Only the closed
 * trigger is ours to style.
 *
 * The count rides in each option's label. It is the point of the facet: it
 * says what picking this instead would give, which is why the API drops a
 * dimension's own filter before counting it.
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

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-3">
        <SearchBox value={state.q} onCommit={(q) => onChange({ q })} />

        <FilterSelect
          label="Show"
          value={state.holding}
          resting={state.holding === EMPTY_FILTER.holding}
          options={HOLDINGS.map((holding) => ({
            value: holding.value,
            label: withCount(holding.label, holdings.get(holding.value)),
          }))}
          onChange={(holding) => onChange({ holding: holding as Holding })}
        />

        <FilterSelect
          label="Order"
          value={state.sort}
          resting={state.sort === EMPTY_FILTER.sort}
          options={SORTS.map((sort) => ({
            value: sort.value,
            label: sort.label,
            // Ranking by match needs something to match against, and the API
            // refuses the pair outright rather than reorder silently.
            disabled: sort.value === "relevance" && state.q.trim() === "",
          }))}
          onChange={(sort) => onChange({ sort: sort as Sort })}
        />

        <BucketSelect
          label="Field"
          anyLabel="Any field"
          buckets={facets?.categories}
          selected={state.category}
          format={(value) => value}
          onSelect={(category) => onChange({ category })}
        />
        <BucketSelect
          label="Month posted"
          anyLabel="Any month"
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

/** "cs.CV" and 12,430 as one option label, because a native option is one
 * text node: there is no second column to right-align a count into. */
function withCount(label: string, count: number | undefined): string {
  return count === undefined ? label : `${label} · ${count.toLocaleString()}`;
}

type Option = { value: string; label: string; disabled?: boolean };

function FilterSelect({
  label,
  value,
  resting,
  options,
  onChange,
}: {
  label: string;
  value: string;
  /** This value is the section's default, so being on it is not a choice the
   * reader made. Teal on a trigger means "you narrowed something". */
  resting?: boolean;
  options: Option[];
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="text-muted px-0.5 font-mono text-[10px] tracking-[0.14em] uppercase"
      >
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={cn(
            // 16px until `md`: iOS Safari zooms the page when a focused
            // control is under 16px and does not undo the zoom on blur.
            "w-full appearance-none rounded border py-2 pr-7 pl-2.5 text-[16px] transition-colors outline-none md:text-[13px] motion-reduce:transition-none",
            resting
              ? "border-line bg-paper text-ink hover:border-ink/30"
              : "border-teal-ink/30 bg-teal-soft text-teal-ink hover:bg-teal-soft-strong font-medium",
          )}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown
          className={cn(
            "pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2",
            resting ? "text-muted" : "text-teal-ink",
          )}
          aria-hidden
        />
      </div>
    </div>
  );
}

/** A facet dimension as a select, with "Any" as its resting value. */
function BucketSelect({
  label,
  anyLabel,
  buckets,
  selected,
  format,
  onSelect,
}: {
  label: string;
  anyLabel: string;
  buckets: CatalogBucket[] | undefined;
  selected: string | null;
  format: (value: string) => string;
  onSelect: (value: string | null) => void;
}) {
  if (!buckets || buckets.length === 0) return null;
  return (
    <FilterSelect
      label={label}
      value={selected ?? ""}
      resting={selected === null}
      options={[
        { value: "", label: anyLabel },
        ...buckets.map((bucket) => ({
          value: bucket.value,
          label: withCount(format(bucket.value), bucket.papers),
        })),
      ]}
      onChange={(value) => onSelect(value === "" ? null : value)}
    />
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
