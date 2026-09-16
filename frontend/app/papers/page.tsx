"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";

import {
  CatalogFilters,
  EMPTY_FILTER,
  HOLDINGS,
  SORTS,
  type CatalogFilterState,
  type Holding,
  type Sort,
} from "@/components/catalog/catalog-filters";
import { CatalogResults } from "@/components/catalog/catalog-results";
import { CatalogSearch } from "@/components/catalog/catalog-search";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { ShellSidebar } from "@/components/shell/shell-sidebar";
import { SiteFooter } from "@/components/site-footer";
import { fetchCatalogFacets, fetchCatalogPapers } from "@/lib/api-client";

/** Every paper in the catalog, filtered — the third STATIC route (§4c
 * decision 2; still no dynamic segments).
 *
 * This is the one list surface that is not indexed-only. The dashboard counts
 * the whole corpus but can only offer the papers the agent reads, which
 * leaves the other 64,692 visible as arithmetic and unreachable as papers.
 * Here they are reachable: a row we indexed opens the reader, and a row we
 * did not opens arXiv, version-pinned. See the D16 amendment.
 *
 * No model runs behind this page. The filter is SQL and BM25 over titles and
 * abstracts, which exist for every catalog row, so it works on papers whose
 * PDF was never fetched — which is most of them.
 *
 * Shape is the dashboard's shell because it IS the dashboard's shell: the
 * same `ShellSidebar`, with this view's filter mounted under the nav rather
 * than in a rail of its own. Explore and Overview are two views of one app,
 * and the rail is where you switch between them.
 *
 * The URL is the filter's only home: no store mirrors it, so there is no
 * store-versus-URL race to resolve, and every view is a link someone can
 * send.
 */
export default function CatalogPage() {
  return (
    <Suspense fallback={null}>
      <Catalog />
    </Suspense>
  );
}

const HOLDING_VALUES = HOLDINGS.map((holding) => holding.value);
const SORT_VALUES = SORTS.map((sort) => sort.value);

function Catalog() {
  const router = useRouter();
  const params = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);

  const state: CatalogFilterState = useMemo(() => {
    const holding = params.get("holding");
    const sort = params.get("sort");
    return {
      q: params.get("q") ?? "",
      category: params.get("category"),
      month: params.get("month"),
      holding: (HOLDING_VALUES.includes(holding as Holding) ? holding : "all") as Holding,
      sort: (SORT_VALUES.includes(sort as Sort) ? sort : "newest") as Sort,
    };
  }, [params]);

  const change = useCallback(
    (next: Partial<CatalogFilterState>) => {
      const merged = { ...state, ...next };
      // Ranking by match has nothing to rank when the query goes away, and
      // the API says so with a 422. Fall back rather than send it.
      if (merged.sort === "relevance" && merged.q.trim() === "") merged.sort = "newest";
      // A first query with no order chosen yet is almost always a relevance
      // question, so the search picks that order. A reader who has since
      // chosen an order keeps it.
      if (next.q !== undefined && next.q.trim() !== "" && state.q.trim() === "") {
        merged.sort = "relevance";
      }
      const search = new URLSearchParams();
      if (merged.q.trim() !== "") search.set("q", merged.q);
      if (merged.category) search.set("category", merged.category);
      if (merged.month) search.set("month", merged.month);
      if (merged.holding !== EMPTY_FILTER.holding) search.set("holding", merged.holding);
      if (merged.sort !== EMPTY_FILTER.sort) search.set("sort", merged.sort);
      const qs = search.toString();
      // `replace`, not `push`: a filter is one page's view, and a reader who
      // changed four rows wants the back button to leave the page, not walk
      // back through four of their own clicks. The URL still carries the
      // whole view, so the link is shareable either way.
      router.replace(qs ? `/papers?${qs}` : "/papers", { scroll: false });
    },
    [router, state],
  );

  const query = useMemo(
    () => ({
      q: state.q.trim() || undefined,
      category: state.category ?? undefined,
      month: state.month ?? undefined,
      holding: state.holding,
      sort: state.sort,
    }),
    [state],
  );

  const papers = useInfiniteQuery({
    queryKey: ["catalog", query],
    queryFn: ({ pageParam }) => fetchCatalogPapers({ ...query, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });
  const { data: facets } = useQuery({
    queryKey: ["catalog-facets", query.q, query.category, query.month, query.holding],
    queryFn: () =>
      fetchCatalogFacets({
        q: query.q,
        category: query.category,
        month: query.month,
        holding: query.holding,
      }),
  });

  const rows = papers.data?.pages.flatMap((page) => page.papers) ?? [];
  const total = papers.data?.pages[0]?.total ?? 0;

  return (
    <div className="bg-paper text-ink flex h-dvh flex-col">
      <div className="flex min-h-0 flex-1">
        <DrawerPanel
          dockAt="md"
          side="left"
          label="Navigation and filters"
          open={filtersOpen}
          onClose={() => setFiltersOpen(false)}
          // Wider as a drawer than as a docked rail: the phone control is 16px
          // (iOS zooms anything smaller) and a facet label carries its count,
          // so "Everything arXiv posted · 65,503" ran off the 264px edge with
          // no ellipsis, which a native select truncates silently.
          className="bg-panel border-line w-[min(320px,86vw)] shrink-0 border-r md:w-[264px]"
        >
          <ShellSidebar current="explore">
            <CatalogFilters
              state={state}
              facets={facets}
              onChange={(next) => {
                change(next);
                setFiltersOpen(false);
              }}
            />
          </ShellSidebar>
        </DrawerPanel>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="bg-panel border-line flex h-[57px] shrink-0 items-center gap-3 border-b px-4">
            <button
              type="button"
              onClick={() => setFiltersOpen(true)}
              aria-label="Open navigation and filters"
              aria-expanded={filtersOpen}
              className="border-line text-ink hover:bg-paper -ml-1 flex size-9 shrink-0 items-center justify-center rounded border transition-colors motion-reduce:transition-none md:hidden"
            >
              <SlidersHorizontal className="size-4" aria-hidden />
            </button>

            <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
              <ol className="flex min-w-0 items-center gap-2 font-mono text-[11.5px]">
                <li className="text-muted hidden sm:block">askRAG</li>
                <li aria-hidden className="text-line hidden sm:block">
                  /
                </li>
                <li className="text-ink font-medium">Explore</li>
              </ol>
            </nav>
          </header>

          <main className="min-h-0 flex-1 overflow-y-auto">
            {/* Narrower than the dashboard's 1280: this canvas is one column of
                  running prose, and the abstract's measure stops near 76
                  characters either way. A wider panel only adds empty space
                  to the right of every line. */}
            <div className="mx-auto flex w-full max-w-[940px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-6">
              {/* Above the results, not in the rail: it is the only control
                  that takes the reader's own words, and the count it moves
                  sits one line below it. It stays put on an error too, so a
                  failed fetch is something to retype through rather than a
                  dead page. */}
              <CatalogSearch value={state.q} onCommit={(q) => change({ q })} />

              {papers.isError ? (
                <p className="text-ink-2 py-16 text-center text-[13.5px]">
                  Could not reach the catalog. The API may still be starting up.
                </p>
              ) : (
                <CatalogResults
                  papers={rows}
                  total={total}
                  state={state}
                  loading={papers.isPending || papers.isFetchingNextPage}
                  onLoadMore={papers.hasNextPage ? () => void papers.fetchNextPage() : null}
                />
              )}
              <SiteFooter />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
