"use client";

import { useEffect, useMemo, useRef } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { usePapersQuery, type PapersQueryFilters } from "@/hooks/use-papers-query";
import { useViewerStore, type SortOption } from "@/stores/viewer-store";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/api-types.gen";

type PaperListItem = components["schemas"]["PaperListItem"];

const ROW_HEIGHT_ESTIMATE_PX = 58;
const OVERSCAN = 12;
// How close (in rows) the last rendered row can be to the end of the loaded
// set before the next page is requested (D-1: infinite scroll, never all
// 6,460 at once).
const FETCH_NEXT_THRESHOLD = 8;

// Fixed pixel widths for every column except "title" (which flexes) — shared
// between the header row and every virtualized body row so the two stay
// column-aligned. Rows are absolutely positioned divs (not a real <table>):
// an HTML table's column-width negotiation only works when every row shares
// one layout pass, which virtualization — rendering a handful of rows at
// arbitrary DOM positions — breaks by construction. This is TanStack
// Virtual's own documented pattern for a virtualized table.
const COLUMN_WIDTH_PX: Record<string, number> = {
  year: 46,
  category: 62,
  rigor: 50,
  arxiv_id: 108,
};

function toggleYearSort(current: SortOption | null): SortOption {
  return current === "year_desc" ? "year_asc" : "year_desc";
}

function toggleTitleSort(current: SortOption | null): SortOption | null {
  return current === "title_asc" ? null : "title_asc";
}

function sortArrow(active: boolean, descending: boolean) {
  if (!active) return null;
  return <span aria-hidden="true">{descending ? " ▼" : " ▲"}</span>;
}

// venue_rigor is a continuous 0..1 corpus-diversity score (spec §1), not the
// mockup's placeholder 0-3 integer — this maps it onto the mockup's 3-dot
// display, a display heuristic only (no spec-defined discretization).
function rigorDots(score: number) {
  const filled = Math.max(0, Math.min(3, Math.round(score * 3)));
  return (
    <span className="text-teal-ink text-[10px] tracking-[2px]" aria-label={`rigor ${filled}/3`}>
      {Array.from({ length: 3 }, (_, i) => (
        <span key={i} className={i < filled ? "" : "text-line"}>
          ●
        </span>
      ))}
    </span>
  );
}

/** TanStack Table + Virtual over `/api/papers` (D-1): only visible rows
 * render, so 6,460 rows scroll at 60fps. Row click sets `viewer-store`'s
 * `paper` (+ URL, via use-viewer-url-sync.ts) — the #29 seam; this
 * component never renders a viewer itself.
 *
 * Rows are dynamically measured (`virtualizer.measureElement`), not a fixed
 * height: paper titles vary from one word to several wrapped lines, and a
 * fixed-height absolutely-positioned row overlaps its neighbor the moment
 * real content exceeds the estimate. `estimateSize` only seeds the initial
 * layout before the first measurement pass. */
export function PaperTable() {
  const q = useViewerStore((state) => state.q);
  const category = useViewerStore((state) => state.category);
  const yearFrom = useViewerStore((state) => state.yearFrom);
  const yearTo = useViewerStore((state) => state.yearTo);
  const sort = useViewerStore((state) => state.sort);
  const setFilters = useViewerStore((state) => state.setFilters);
  const setPaper = useViewerStore((state) => state.setPaper);

  const filters = useMemo<PapersQueryFilters>(
    () => ({ q, category, yearFrom, yearTo, sort }),
    [q, category, yearFrom, yearTo, sort],
  );
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isPending } =
    usePapersQuery(filters);

  const papers = useMemo(() => data?.pages.flatMap((page) => page.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? null;
  const hasRigorData = papers.some((p) => p.facets?.venue_rigor != null);

  const columns = useMemo<ColumnDef<PaperListItem>[]>(() => {
    const cols: ColumnDef<PaperListItem>[] = [
      {
        id: "title",
        header: () => (
          <button
            type="button"
            onClick={() => setFilters({ sort: toggleTitleSort(sort) })}
            className="uppercase"
          >
            Paper
            {sort === "title_asc" && sortArrow(true, false)}
          </button>
        ),
        cell: ({ row }) => (
          <div>
            <span className="font-serif text-[15px]">{row.original.title}</span>
            <span className="text-muted block font-sans text-[11.5px]">{row.original.authors}</span>
          </div>
        ),
      },
      {
        id: "year",
        header: () => (
          <button
            type="button"
            onClick={() => setFilters({ sort: toggleYearSort(sort) })}
            className="uppercase"
          >
            Year
            {sortArrow(sort === "year_desc" || sort === "year_asc", sort !== "year_asc")}
          </button>
        ),
        cell: ({ row }) => (
          <span className="text-muted font-mono text-[11.5px]">{row.original.year}</span>
        ),
      },
      {
        id: "category",
        header: () => <span className="uppercase">Cat</span>,
        cell: ({ row }) => (
          <span className="bg-teal-soft text-teal-ink rounded px-1.5 py-0.5 font-mono text-[10.5px]">
            {row.original.primary_category}
          </span>
        ),
      },
    ];

    // D-3 (DECISIONS.md): no column backed by empty data — only shown once
    // at least one loaded row actually carries a venue_rigor score.
    if (hasRigorData) {
      cols.push({
        id: "rigor",
        header: () => <span className="uppercase">Rigor</span>,
        cell: ({ row }) => {
          const score = row.original.facets?.venue_rigor;
          return typeof score === "number" ? rigorDots(score) : null;
        },
      });
    }

    cols.push({
      id: "arxiv_id",
      header: () => <span className="uppercase">arXiv id</span>,
      cell: ({ row }) => (
        <span className="text-muted font-mono text-[11.5px] whitespace-nowrap">
          {row.original.arxiv_id}
          {row.original.version ?? ""}
        </span>
      ),
    });

    return cols;
  }, [sort, hasRigorData, setFilters]);

  const table = useReactTable({
    data: papers,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.arxiv_id,
  });
  const rows = table.getRowModel().rows;
  const headerCells = table.getFlatHeaders();

  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_ESTIMATE_PX,
    overscan: OVERSCAN,
  });
  const virtualRows = virtualizer.getVirtualItems();

  useEffect(() => {
    const last = virtualRows[virtualRows.length - 1];
    if (!last) return;
    if (
      last.index >= rows.length - 1 - FETCH_NEXT_THRESHOLD &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      void fetchNextPage();
    }
  }, [virtualRows, rows.length, hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="text-muted px-3 pt-2.5 pb-1.5 font-mono text-[11.5px] sm:px-5">
        {isPending
          ? "loading…"
          : total !== null
            ? `showing ${papers.length} of ${total.toLocaleString()} (virtualized)`
            : `showing ${papers.length} search results (virtualized)`}
      </div>

      {/* Sorting lives in the column headers, which the card layout drops —
          so below `md:` it gets its own control rather than becoming
          unreachable. */}
      <div className="flex items-center gap-2 px-3 pb-2 md:hidden">
        <span className="text-muted font-mono text-[10.5px] font-semibold tracking-[0.1em] uppercase">
          Sort
        </span>
        <button
          type="button"
          onClick={() => setFilters({ sort: toggleYearSort(sort) })}
          aria-pressed={sort === "year_desc" || sort === "year_asc"}
          className={cn(
            "border-line rounded border px-2.5 py-1 font-mono text-[11.5px]",
            sort === "year_desc" || sort === "year_asc"
              ? "bg-teal-soft text-teal-ink border-teal-ink"
              : "text-muted",
          )}
        >
          Year{sortArrow(sort === "year_desc" || sort === "year_asc", sort !== "year_asc")}
        </button>
        <button
          type="button"
          onClick={() => setFilters({ sort: toggleTitleSort(sort) })}
          aria-pressed={sort === "title_asc"}
          className={cn(
            "border-line rounded border px-2.5 py-1 font-mono text-[11.5px]",
            sort === "title_asc" ? "bg-teal-soft text-teal-ink border-teal-ink" : "text-muted",
          )}
        >
          Title{sortArrow(sort === "title_asc", false)}
        </button>
      </div>
      <div
        role="table"
        aria-label="Corpus papers"
        className="border-line mx-3 mb-3 flex min-h-0 flex-1 flex-col border-t sm:mx-5 sm:mb-5"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        <div role="rowgroup" className="border-ink hidden border-b-[1.5px] md:flex">
          <div role="row" className="flex w-full">
            {headerCells.map((header) => (
              <div
                key={header.id}
                role="columnheader"
                className="bg-paper text-muted overflow-hidden px-1.5 py-2 text-left font-mono text-[10.5px] font-semibold tracking-[0.1em] whitespace-nowrap"
                style={
                  header.column.id === "title"
                    ? { flex: "1 1 0%", minWidth: 0 }
                    : { flex: `0 0 ${COLUMN_WIDTH_PX[header.column.id]}px` }
                }
              >
                {flexRender(header.column.columnDef.header, header.getContext())}
              </div>
            ))}
          </div>
        </div>
        <div ref={parentRef} role="rowgroup" className="flex-1 overflow-y-auto">
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualRows.map((virtualRow) => {
              const row = rows[virtualRow.index];
              return (
                <div
                  key={row.id}
                  data-index={virtualRow.index}
                  ref={virtualizer.measureElement}
                  role="row"
                  tabIndex={0}
                  onClick={() => setPaper(row.original.arxiv_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setPaper(row.original.arxiv_id);
                    }
                  }}
                  className="border-line hover:bg-panel flex w-full cursor-pointer border-b"
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  {/* Card below `md:`. The fixed columns total 266px, which
                      at 390px viewport width leaves the title about 120px —
                      one or two words per line. Same row element, same
                      measured height, no second data path: both layouts read
                      `row.original`. */}
                  <div role="cell" className="flex min-w-0 flex-col gap-1 px-2 py-2.5 md:hidden">
                    <span className="font-serif text-[15px] leading-snug">
                      {row.original.title}
                    </span>
                    <span className="text-muted line-clamp-1 font-sans text-[11.5px]">
                      {row.original.authors}
                    </span>
                    <div className="text-muted flex items-center gap-2 font-mono text-[11px]">
                      <span>{row.original.year}</span>
                      <span className="bg-teal-soft text-teal-ink rounded px-1.5 py-0.5 text-[10.5px]">
                        {row.original.primary_category}
                      </span>
                      {typeof row.original.facets?.venue_rigor === "number" &&
                        rigorDots(row.original.facets.venue_rigor)}
                      <span className="ml-auto whitespace-nowrap">
                        {row.original.arxiv_id}
                        {row.original.version ?? ""}
                      </span>
                    </div>
                  </div>

                  <div className="hidden w-full md:flex">
                    {row.getVisibleCells().map((cell) => (
                      <div
                        key={cell.id}
                        role="cell"
                        className={cn(
                          "px-1.5 py-2.5",
                          cell.column.id === "title" ? "min-w-0" : "overflow-hidden",
                        )}
                        style={
                          cell.column.id === "title"
                            ? { flex: "1 1 0%", minWidth: 0 }
                            : { flex: `0 0 ${COLUMN_WIDTH_PX[cell.column.id]}px` }
                        }
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {!isPending && papers.length === 0 && (
          <p className="text-muted mt-6 px-2.5 text-sm">No papers match the current filters.</p>
        )}
      </div>
    </div>
  );
}
