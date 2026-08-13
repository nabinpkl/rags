"use client";

import { CorpusSearchBar } from "@/components/explorer/corpus-search-bar";
import { FacetFilters } from "@/components/explorer/facet-filters";
import { PaperTable } from "@/components/explorer/paper-table";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { useUiShellStore } from "@/stores/ui-shell-store";

/** Composes the explorer region (facet rail + search + virtualized table) —
 * mirrors chat-panel.tsx's role for the agent panel: composition only, no
 * fetching/parsing/URL logic of its own.
 *
 * The rail docks from `md:` and is a left drawer below it (#83), opened from
 * `app-bar.tsx`'s hamburger. The drawer lives here rather than in the shell
 * because filters are explorer state: in the viewer there is nothing for them
 * to filter, and the bar hides its own button there to match.
 *
 * The store<->URL sync subscription (D-2) moved to `AppRegion` in
 * `app/page.tsx` (#29): this component now mounts/unmounts as
 * `viewer-store`'s `paper` toggles (explorer <-> viewer swap), and the sync
 * owner can't live on a component that unmounts as a DIRECT CONSEQUENCE of
 * the very store change it exists to react to — a row click's `setPaper`
 * would unmount this component (and its hook instance) in the same commit
 * that was supposed to push the new `?paper=` URL, dropping the push.
 * `AppRegion` spans both regions and never unmounts, so it owns the one
 * subscription instead. */
export function ExplorerPanel() {
  const overlay = useUiShellStore((state) => state.overlay);
  const closeOverlay = useUiShellStore((state) => state.closeOverlay);

  return (
    <div className="bg-paper flex h-full min-w-0">
      <DrawerPanel
        dockAt="md"
        side="left"
        label="Facet filters"
        open={overlay === "filters"}
        onClose={closeOverlay}
        className="w-[min(84vw,280px)] md:h-full md:w-[216px]"
      >
        <FacetFilters />
      </DrawerPanel>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Wraps below `sm:`: at 390px a heading plus a full search field on
            one row leaves the input about 120px wide. */}
        <div className="border-line flex flex-wrap items-center gap-x-3 gap-y-2 border-b px-3 py-2.5 sm:px-5 sm:py-3">
          <h1 className="text-ink font-serif text-[19px] font-semibold">Corpus</h1>
          <CorpusSearchBar />
        </div>
        <PaperTable />
      </div>
    </div>
  );
}
