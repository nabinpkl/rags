"use client";

import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import {
  EMPTY_FILTER,
  HOLDINGS,
  SORTS,
  type CatalogFilterState,
  type Holding,
  type Sort,
} from "@/components/catalog/catalog-filters";
import { fetchCatalogFacets, fetchCatalogPapers } from "@/lib/api-client";

const HOLDING_VALUES = HOLDINGS.map((holding) => holding.value);
const SORT_VALUES = SORTS.map((sort) => sort.value);

/** The catalog filter, read from and written to the URL, and the two queries
 * it drives. Shared by Explore and the RAG demo, which are the same list over
 * different scopes.
 *
 * The URL is the filter's only home: no store mirrors it, so there is no
 * store-versus-URL race to resolve, and every view is a link someone can
 * send.
 *
 * `pinnedHolding` fixes the scope for a view that exists to show one slice.
 * It is never read from or written to the URL, so a hand-edited `?holding=`
 * cannot widen the demo past the papers its agent can read. */
export function catalogSearchParams(
  merged: CatalogFilterState,
  pinnedHolding?: Holding,
): URLSearchParams {
  const search = new URLSearchParams();
  if (merged.q.trim() !== "") search.set("q", merged.q);
  if (merged.category) search.set("category", merged.category);
  if (merged.month) search.set("month", merged.month);
  if (pinnedHolding === undefined && merged.holding !== EMPTY_FILTER.holding) {
    search.set("holding", merged.holding);
  }
  if (merged.sort !== EMPTY_FILTER.sort) search.set("sort", merged.sort);
  return search;
}

/** Applies a partial change to the current filter, with the two ordering
 * rules the API and the reader both expect. */
export function mergeCatalogFilter(
  state: CatalogFilterState,
  next: Partial<CatalogFilterState>,
): CatalogFilterState {
  const merged = { ...state, ...next };
  // Ranking by match has nothing to rank when the query goes away, and the
  // API says so with a 422. Fall back rather than send it.
  if (merged.sort === "relevance" && merged.q.trim() === "") merged.sort = "newest";
  // A first query with no order chosen yet is almost always a relevance
  // question, so the search picks that order. A reader who has since chosen
  // an order keeps it.
  if (next.q !== undefined && next.q.trim() !== "" && state.q.trim() === "") {
    merged.sort = "relevance";
  }
  return merged;
}

export function useCatalogQuery({ pinnedHolding }: { pinnedHolding?: Holding } = {}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const state: CatalogFilterState = useMemo(() => {
    const holding = params.get("holding");
    const sort = params.get("sort");
    return {
      q: params.get("q") ?? "",
      category: params.get("category"),
      month: params.get("month"),
      holding:
        pinnedHolding ??
        ((HOLDING_VALUES.includes(holding as Holding) ? holding : "all") as Holding),
      sort: (SORT_VALUES.includes(sort as Sort) ? sort : "newest") as Sort,
    };
  }, [params, pinnedHolding]);

  const change = useCallback(
    (next: Partial<CatalogFilterState>) => {
      const qs = catalogSearchParams(mergeCatalogFilter(state, next), pinnedHolding).toString();
      // `replace`, not `push`: a filter is one page's view, and a reader who
      // changed four rows wants the back button to leave the page, not walk
      // back through four of their own clicks. The URL still carries the
      // whole view, so the link is shareable either way.
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, state, pinnedHolding],
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
  const facets = useQuery({
    queryKey: ["catalog-facets", query.q, query.category, query.month, query.holding],
    queryFn: () =>
      fetchCatalogFacets({
        q: query.q,
        category: query.category,
        month: query.month,
        holding: query.holding,
      }),
    // The rail keeps the last counts while the next ones load. Without this
    // every pick unmounted the month and topic controls for a round trip,
    // and the rail collapsed under the reader's pointer.
    placeholderData: keepPreviousData,
  });

  return { state, change, papers, facets: facets.data };
}
