"use client";

import { useCallback, useEffect, useState } from "react";
import { useFacetsQuery } from "@/hooks/use-papers-query";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";
import { cn } from "@/lib/utils";

const DEBOUNCE_MS = 400;

// 16px below `md:`: iOS Safari zooms the whole page when a focused input's
// font-size is under 16px, and the zoom does not undo on blur.
const YEAR_INPUT_CLASS =
  "border-line bg-paper text-ink w-full rounded border px-2 py-2 font-mono text-[16px] outline-none md:py-1 md:text-[11.5px]";

/** Local text buffer for a debounced year input — mirrors
 * corpus-search-bar.tsx's pattern (render-time resync for external changes,
 * a debounced commit effect for local edits) so typing a year doesn't push
 * a browser-history entry per keystroke. use-viewer-url-sync.ts uses
 * `router.push`, not `replace`, so every filter change is back-button
 * navigable (§4c decision 2) — debouncing here is what keeps that from
 * spamming history while typing. */
function useDebouncedYearInput(
  committed: number | null,
  commit: (value: number | null) => void,
): [string, (raw: string) => void] {
  const [value, setValue] = useState(committed === null ? "" : String(committed));
  const [synced, setSynced] = useState(committed);

  if (committed !== synced) {
    setSynced(committed);
    setValue(committed === null ? "" : String(committed));
  }

  useEffect(() => {
    const parsed = value === "" ? null : Number(value);
    if (parsed === committed || Number.isNaN(parsed)) return;
    const timer = setTimeout(() => commit(parsed), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value, committed, commit]);

  return [value, setValue];
}

/** Category buttons + a year range, reading `GET /api/facets` for counts
 * (the CATEGORICAL facet sense, DECISIONS.md #27 Fill-in 2 — distinct from
 * paper-table.tsx's diversity-score `facets=`) and writing viewer-store
 * filter state. Counts/buckets reflect the current category+year filters
 * uniformly (no exclude-own-dimension faceting yet, per that entry's
 * consequence note). */
export function FacetFilters() {
  const category = useViewerStore((state) => state.category);
  const yearFrom = useViewerStore((state) => state.yearFrom);
  const yearTo = useViewerStore((state) => state.yearTo);
  const setFilters = useViewerStore((state) => state.setFilters);
  const closeOverlay = useUiShellStore((state) => state.closeOverlay);

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

  // Stable callback identities (deps: `setFilters` alone, a stable zustand
  // action ref) so useDebouncedYearInput's commit effect only resets its
  // timer when `value`/`committed` actually change — not on every unrelated
  // re-render (e.g. a facets refetch), which an inline arrow here would
  // otherwise cause by changing `commit`'s identity every render.
  const commitYearFrom = useCallback(
    (value: number | null) => setFilters({ yearFrom: value }),
    [setFilters],
  );
  const commitYearTo = useCallback(
    (value: number | null) => setFilters({ yearTo: value }),
    [setFilters],
  );
  const [yearFromInput, setYearFromInput] = useDebouncedYearInput(yearFrom, commitYearFrom);
  const [yearToInput, setYearToInput] = useDebouncedYearInput(yearTo, commitYearTo);

  function toggleCategory(value: string) {
    setFilters({ category: category === value ? null : value });
  }

  return (
    // Fills whatever box drawer-panel.tsx put it in; that element carries the
    // region/dialog role and the "Facet filters" name, so this one stays a
    // plain div rather than a second labelled landmark.
    <div className="bg-panel border-line flex h-full min-h-0 flex-col border-r">
      {/* Only reachable when this is a drawer — `hidden` (not just visually
          hidden) so the docked rail doesn't leave a dead tab stop. */}
      <div className="border-line flex items-center justify-between border-b px-3.5 py-2 md:hidden">
        <span className="text-muted font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase">
          Filters
        </span>
        <button
          type="button"
          onClick={closeOverlay}
          aria-label="Close facet filters"
          className="text-muted hover:text-ink flex h-9 w-9 items-center justify-center text-lg"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3.5">
        <h3 className="text-muted mt-0 mb-2 font-mono text-[10.5px] font-semibold tracking-[0.12em] uppercase">
          Category
        </h3>
        <button
          type="button"
          aria-pressed={category === null}
          onClick={() => setFilters({ category: null })}
          className={cn(
            "flex items-center justify-between rounded px-2 py-2.5 text-left text-[13px] md:py-1.5",
            category === null ? "bg-teal-soft text-teal-ink font-semibold" : "hover:bg-paper",
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
              "flex items-center justify-between rounded px-2 py-2.5 text-left text-[13px] md:py-1.5",
              category === bucket.value
                ? "bg-teal-soft text-teal-ink font-semibold"
                : "hover:bg-paper",
            )}
          >
            <span>{bucket.value}</span>
            <span className="text-muted font-mono text-[11px]">
              {bucket.count.toLocaleString()}
            </span>
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
            value={yearFromInput}
            onChange={(event) => setYearFromInput(event.target.value)}
            placeholder="from"
            aria-label="From year"
            className={YEAR_INPUT_CLASS}
          />
          <input
            type="number"
            value={yearToInput}
            onChange={(event) => setYearToInput(event.target.value)}
            placeholder="to"
            aria-label="To year"
            className={YEAR_INPUT_CLASS}
          />
        </div>
      </div>
    </div>
  );
}
