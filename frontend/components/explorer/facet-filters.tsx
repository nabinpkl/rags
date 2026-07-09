"use client";

import { useFacetsQuery } from "@/hooks/use-papers-query";
import { useViewerStore } from "@/stores/viewer-store";
import { cn } from "@/lib/utils";

/** Category buttons + a year range, reading `GET /api/facets` for counts
 * (the CATEGORICAL facet sense, decisions.md #27 Fill-in 2 — distinct from
 * paper-table.tsx's diversity-score `facets=`) and writing viewer-store
 * filter state. Counts/buckets reflect the current category+year filters
 * uniformly (no exclude-own-dimension faceting yet, per that entry's
 * consequence note). */
export function FacetFilters() {
  const category = useViewerStore((state) => state.category);
  const yearFrom = useViewerStore((state) => state.yearFrom);
  const yearTo = useViewerStore((state) => state.yearTo);
  const setFilters = useViewerStore((state) => state.setFilters);

  const { data } = useFacetsQuery({ category, yearFrom, yearTo });
  const categoryBuckets = (data?.category.buckets ?? []).filter((b) => b.value !== null);
  const yearBuckets = (data?.year.buckets ?? []).filter(
    (b): b is { value: number; count: number } => typeof b.value === "number",
  );
  const sortedYears = [...yearBuckets].sort((a, b) => a.value - b.value);
  const maxYearCount = Math.max(1, ...sortedYears.map((b) => b.count));
  const yearRangeLabel =
    sortedYears.length > 0
      ? `${sortedYears[0].value}–${sortedYears[sortedYears.length - 1].value}`
      : null;

  function toggleCategory(value: string) {
    setFilters({ category: category === value ? null : value });
  }

  function onYearFromChange(raw: string) {
    setFilters({ yearFrom: raw === "" ? null : Number(raw) });
  }

  function onYearToChange(raw: string) {
    setFilters({ yearTo: raw === "" ? null : Number(raw) });
  }

  return (
    <aside
      aria-label="Facet filters"
      className="bg-panel border-line flex w-[216px] shrink-0 flex-col overflow-y-auto border-r p-3.5"
    >
      <h3 className="text-muted mt-0 mb-2 font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase">
        Category
      </h3>
      <button
        type="button"
        aria-pressed={category === null}
        onClick={() => setFilters({ category: null })}
        className={cn(
          "flex items-center justify-between rounded px-2 py-1.5 text-left text-[13px]",
          category === null ? "bg-teal-soft text-teal-deep font-semibold" : "hover:bg-paper",
        )}
      >
        <span>all</span>
        {data && (
          <span className="text-muted font-mono text-[11px]">{data.total.toLocaleString()}</span>
        )}
      </button>
      {categoryBuckets.map((bucket) => (
        <button
          key={String(bucket.value)}
          type="button"
          aria-pressed={category === bucket.value}
          onClick={() => toggleCategory(String(bucket.value))}
          className={cn(
            "flex items-center justify-between rounded px-2 py-1.5 text-left text-[13px]",
            category === bucket.value
              ? "bg-teal-soft text-teal-deep font-semibold"
              : "hover:bg-paper",
          )}
        >
          <span>{bucket.value}</span>
          <span className="text-muted font-mono text-[11px]">{bucket.count.toLocaleString()}</span>
        </button>
      ))}

      <h3 className="text-muted mt-4.5 mb-2 font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase">
        Years{yearRangeLabel ? ` · ${yearRangeLabel}` : ""}
      </h3>
      {sortedYears.length > 0 && (
        <div className="mb-1.5 flex h-11 items-end gap-0.5" aria-hidden="true">
          {sortedYears.map((bucket) => (
            <span
              key={bucket.value}
              className={cn(
                "bg-line min-h-[3px] flex-1 rounded-t-[1px]",
                yearFrom !== null && bucket.value < yearFrom
                  ? "bg-line"
                  : yearTo !== null && bucket.value > yearTo
                    ? "bg-line"
                    : "bg-teal",
              )}
              style={{ height: `${8 + Math.round(36 * (bucket.count / maxYearCount))}px` }}
            />
          ))}
        </div>
      )}
      <div className="flex gap-1.5">
        <input
          type="number"
          value={yearFrom ?? ""}
          onChange={(event) => onYearFromChange(event.target.value)}
          placeholder="from"
          aria-label="From year"
          className="border-line bg-paper text-ink w-full rounded border px-2 py-1 font-mono text-[11.5px] outline-none"
        />
        <input
          type="number"
          value={yearTo ?? ""}
          onChange={(event) => onYearToChange(event.target.value)}
          placeholder="to"
          aria-label="To year"
          className="border-line bg-paper text-ink w-full rounded border px-2 py-1 font-mono text-[11.5px] outline-none"
        />
      </div>
    </aside>
  );
}
