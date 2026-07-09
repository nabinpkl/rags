"use client";

import { CorpusSearchBar } from "@/components/explorer/corpus-search-bar";
import { FacetFilters } from "@/components/explorer/facet-filters";
import { PaperTable } from "@/components/explorer/paper-table";

/** Composes the explorer region (facet rail + search + virtualized table) —
 * mirrors chat-panel.tsx's role for the agent panel: composition only, no
 * fetching/parsing/URL logic of its own.
 *
 * The store<->URL sync subscription (D-2) moved to `viewer-region.tsx`
 * (#29): this component now mounts/unmounts as `viewer-store`'s `paper`
 * toggles (explorer <-> viewer swap), and the sync owner can't live on a
 * component that unmounts as a DIRECT CONSEQUENCE of the very store change
 * it exists to react to — a row click's `setPaper` would unmount this
 * component (and its hook instance) in the same commit that was supposed to
 * push the new `?paper=` URL, dropping the push. `viewer-region.tsx` spans
 * both regions and never unmounts, so it owns the one subscription instead. */
export function ExplorerPanel() {
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
