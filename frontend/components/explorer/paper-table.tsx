"use client";

import { useEffect, useMemo, useRef } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { usePapersQuery, type PapersQueryFilters } from "@/hooks/use-papers-query";
import { useViewerStore, type SortOption } from "@/stores/viewer-store";
import { cn } from "@/lib/utils";
import type { components } from "@/lib/api-types.gen";

type PaperListItem = components["schemas"]["PaperListItem"];

const ROW_HEIGHT_PX = 58;
const OVERSCAN = 12;
// How close (in rows) the last rendered row can be to the end of the loaded
// set before the next page is requested (D-1: infinite scroll, never all
// 6,460 at once).
const FETCH_NEXT_THRESHOLD = 8;

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
    <span className="text-teal-deep text-[10px] tracking-[2px]" aria-label={`rigor ${filled}/3`}>
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
 * component never renders a viewer itself. */
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
          <span className="bg-teal-soft text-teal-deep rounded px-1.5 py-0.5 font-mono text-[10.5px]">
            {row.original.primary_category}
          </span>
        ),
      },
    ];

    // D-3 (decisions.md): no column backed by empty data — only shown once
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

  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_PX,
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
      <div className="text-muted px-5 pt-2.5 pb-1.5 font-mono text-[11.5px]">
        {isPending
          ? "loading…"
          : total !== null
            ? `showing ${papers.length} of ${total.toLocaleString()} (virtualized)`
            : `showing ${papers.length} search results (virtualized)`}
      </div>
      <div ref={parentRef} className="flex-1 overflow-y-auto px-5 pb-5">
        <table className="w-full border-collapse" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="bg-paper text-muted border-ink sticky top-0 border-b-[1.5px] px-2.5 py-2 text-left font-mono text-[10.5px] font-semibold tracking-[0.1em]"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody
            style={{ height: virtualizer.getTotalSize(), position: "relative", display: "block" }}
          >
            {virtualRows.map((virtualRow) => {
              const row = rows[virtualRow.index];
              return (
                <tr
                  key={row.id}
                  onClick={() => setPaper(row.original.arxiv_id)}
                  className="border-line hover:bg-panel cursor-pointer border-b"
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    display: "table",
                    tableLayout: "fixed",
                    width: "100%",
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-2.5 py-2.5 align-baseline">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
        {!isPending && papers.length === 0 && (
          <p className="text-muted mt-6 text-sm">No papers match the current filters.</p>
        )}
      </div>
    </div>
  );
}
