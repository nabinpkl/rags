"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { fetchFacets, fetchPapers } from "@/lib/api-client";
import type { SortOption } from "@/stores/viewer-store";

// D-3 (DECISIONS.md): requested so paper-table.tsx can decide, from real
// response data rather than a guessed dev/prod flag, whether the rigor
// column has anything to show — the five diversity scores depend on the
// #13 embed run and may be null. The other four diversity facets
// (authority/niche_idf/author_novelty/revisions) have no explorer column
// yet; add to this list if a future issue surfaces them.
const REQUESTED_FACETS = "venue_rigor";

export interface PapersQueryFilters {
  q: string;
  category: string | null;
  yearFrom: number | null;
  yearTo: number | null;
  sort: SortOption | null;
}

/** D-1 (DECISIONS.md): `useInfiniteQuery` + TanStack Virtual windowing, not
 * fetching all 6,460 rows. `queryKey` includes every filter so changing one
 * starts a fresh accumulation instead of mixing pages across filter sets. */
export function usePapersQuery(filters: PapersQueryFilters) {
  return useInfiniteQuery({
    queryKey: ["papers", filters],
    queryFn: ({ pageParam }) =>
      fetchPapers({
        q: filters.q,
        category: filters.category,
        year_from: filters.yearFrom,
        year_to: filters.yearTo,
        sort: filters.sort,
        facets: REQUESTED_FACETS,
        cursor: pageParam,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });
}

export interface FacetsQueryFilters {
  category: string | null;
  yearFrom: number | null;
  yearTo: number | null;
}

/** Categorical counts for the facet rail — applies the current
 * category/year filters uniformly (DECISIONS.md #27 entry: no
 * exclude-own-dimension faceting yet). */
export function useFacetsQuery(filters: FacetsQueryFilters) {
  return useQuery({
    queryKey: ["facets", filters],
    queryFn: () =>
      fetchFacets({
        category: filters.category,
        year_from: filters.yearFrom,
        year_to: filters.yearTo,
      }),
  });
}
