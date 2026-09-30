"use client";

import { Suspense } from "react";

import { CatalogView } from "@/components/catalog/catalog-view";

/** Every paper in the catalog, filtered — a STATIC route (§4c decision 2;
 * still no dynamic segments).
 *
 * This is the one list surface that is not indexed-only. The overview counts
 * the whole corpus but can only offer the papers the agent reads, which
 * leaves the rest visible as arithmetic and unreachable as papers. Here they
 * are reachable: a card we indexed opens the reader beside the agent on the
 * RAG demo, and a card we did not opens arXiv, version-pinned. See the D16
 * amendment.
 *
 * No model runs behind this page. The filter is SQL and BM25 over titles and
 * abstracts, which exist for every catalog row, so it works on papers whose
 * PDF was never fetched — which is most of them.
 */
export default function CatalogPage() {
  return (
    // `useSearchParams` (via use-catalog-query.ts) needs a boundary in a
    // static export build.
    <Suspense fallback={null}>
      <CatalogView
        view="explore"
        readerHref={(arxivId) => `/demo?paper=${encodeURIComponent(arxivId)}`}
      />
    </Suspense>
  );
}
