"use client";

import { useQuery } from "@tanstack/react-query";
import { Suspense } from "react";

import { CatalogView } from "@/components/catalog/catalog-view";
import { CoverageStrip } from "@/components/catalog/coverage-strip";
import { fetchCoverage } from "@/lib/api-client";

/** The home page: every paper in the catalog, filtered. A STATIC route (§4c
 * decision 2; still no dynamic segments).
 *
 * This is the one list surface that is not indexed-only: a card we indexed
 * opens the reader beside the agent on the RAG demo, and a card we did not
 * opens arXiv, version-pinned. See the D16 amendment.
 *
 * No model runs behind this page. The filter is SQL and BM25 over titles and
 * abstracts, which exist for every catalog row, so it works on papers whose
 * PDF was never fetched, which is most of them.
 */
export default function ExplorePage() {
  const { data: coverage } = useQuery({ queryKey: ["coverage"], queryFn: fetchCoverage });

  return (
    // `useSearchParams` (via use-catalog-query.ts) needs a boundary in a
    // static export build.
    <Suspense fallback={null}>
      <CatalogView
        view="explore"
        readerHref={(arxivId) => `/demo?paper=${encodeURIComponent(arxivId)}`}
        barEnd={coverage && <CoverageStrip coverage={coverage} />}
      />
    </Suspense>
  );
}
