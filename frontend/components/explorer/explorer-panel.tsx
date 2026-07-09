"use client";

import { useViewerUrlSync } from "@/hooks/use-viewer-url-sync";
import { CorpusSearchBar } from "@/components/explorer/corpus-search-bar";
import { FacetFilters } from "@/components/explorer/facet-filters";
import { PaperTable } from "@/components/explorer/paper-table";

/** Composes the explorer region (facet rail + search + virtualized table)
 * and owns the one store<->URL sync subscription (D-2) — mirrors
 * chat-panel.tsx's role for the agent panel: composition only, no
 * fetching/parsing/URL logic of its own. */
export function ExplorerPanel() {
  useViewerUrlSync();

  return (
    <div className="bg-paper flex h-full min-w-0">
      <FacetFilters />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-line flex items-center gap-3 border-b px-5 py-3">
          <h1 className="text-ink font-serif text-[19px] font-semibold">Corpus</h1>
          <CorpusSearchBar />
        </div>
        <PaperTable />
      </div>
    </div>
  );
}
