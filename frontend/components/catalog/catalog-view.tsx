"use client";

import { SlidersHorizontal } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";

import { CatalogFilters, type Holding } from "@/components/catalog/catalog-filters";
import { CatalogResults } from "@/components/catalog/catalog-results";
import { CatalogSearch } from "@/components/catalog/catalog-search";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { ShellSidebar, VIEWS } from "@/components/shell/shell-sidebar";
import { SiteFooter } from "@/components/site-footer";
import { useCatalogQuery } from "@/hooks/use-catalog-query";
import { useIsStuck } from "@/hooks/use-is-stuck";
import { cn } from "@/lib/utils";
import { useUiShellStore } from "@/stores/ui-shell-store";

/** A filtered list of papers inside the app shell: the rail with this view's
 * filter under the nav, a bar naming the view, and a canvas of cards.
 *
 * Explore and the RAG demo are the same list over different scopes, so they
 * are one component rather than two copies of the shell. What the demo adds
 * arrives through props: a pinned scope, an agent column (`aside`), a handle
 * for it (`barEnd`), and the reader, which takes the canvas while a paper is
 * open (`reader`).
 *
 * The left drawer's open state is `ui-shell-store`'s `filters` overlay, not
 * local state: it and the agent sheet are mutually exclusive full-height
 * overlays, which is what that enum exists to guarantee. */
export function CatalogView({
  view,
  readerHref,
  pinnedHolding,
  aside,
  barEnd,
  reader,
  heading,
}: {
  view: "explore" | "demo";
  readerHref: (arxivId: string) => string;
  pinnedHolding?: Holding;
  aside?: ReactNode;
  barEnd?: ReactNode;
  /** Rendered in place of the list while a paper is open. */
  reader?: ReactNode;
  heading?: { title: string; subtitle: string };
}) {
  const { state, change, papers, facets } = useCatalogQuery({ pinnedHolding });
  const overlay = useUiShellStore((s) => s.overlay);
  const openFilters = useUiShellStore((s) => s.openFilters);
  const closeOverlay = useUiShellStore((s) => s.closeOverlay);
  // State, not a ref: the results list windows against this node and can
  // mount in the same commit (see `use-infinite-virtual-list.ts`).
  const [canvas, setCanvas] = useState<HTMLElement | null>(null);
  const searchRestRef = useRef<HTMLDivElement>(null);
  const searchStuck = useIsStuck(searchRestRef, canvas);

  const rows = papers.data?.pages.flatMap((page) => page.papers) ?? [];
  const total = papers.data?.pages[0]?.total ?? 0;
  const label = VIEWS.find((entry) => entry.id === view)?.label ?? view;

  return (
    <div className="bg-paper text-ink flex h-dvh flex-col">
      <div className="flex min-h-0 flex-1">
        <DrawerPanel
          dockAt="md"
          side="left"
          label="Navigation and filters"
          open={overlay === "filters"}
          onClose={closeOverlay}
          // Wider as a drawer than as a docked rail: the phone control is 16px
          // (iOS zooms anything smaller) and a facet label carries its count,
          // so a long label ran off the 264px edge with no ellipsis, which a
          // native select truncates silently.
          className="bg-panel border-line w-[min(320px,86vw)] shrink-0 border-r md:w-[264px]"
        >
          <ShellSidebar current={view}>
            <CatalogFilters
              state={state}
              facets={facets}
              onChange={(next) => {
                change(next);
                closeOverlay();
              }}
            />
          </ShellSidebar>
        </DrawerPanel>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="bg-panel border-line flex h-[57px] shrink-0 items-center gap-3 border-b px-4">
            <button
              type="button"
              onClick={openFilters}
              aria-label="Open navigation and filters"
              aria-expanded={overlay === "filters"}
              className="border-line text-ink hover:bg-panel-hover -ml-1 flex size-9 shrink-0 items-center justify-center rounded border transition-colors motion-reduce:transition-none md:hidden"
            >
              <SlidersHorizontal className="size-4" aria-hidden />
            </button>

            <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
              <ol className="flex min-w-0 items-center gap-2 font-mono text-[11.5px]">
                <li className="text-muted hidden sm:block">askRAG</li>
                <li aria-hidden className="text-line hidden sm:block">
                  /
                </li>
                <li className="text-ink font-medium">{label}</li>
              </ol>
            </nav>

            {barEnd}
          </header>

          {reader ? (
            <div className="min-h-0 flex-1">{reader}</div>
          ) : (
            <main ref={setCanvas} className="min-h-0 flex-1 overflow-y-auto">
              {/* Narrower than the dashboard's 1280: this canvas is one column
                  of running prose, and the abstract's measure stops near 76
                  characters either way. */}
              <div className="relative mx-auto flex w-full max-w-[940px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-6">
                {/* Where the search band's top edge rests: the column's top
                    padding less the band's 12px pull-up. Once this pixel
                    scrolls out, the band is pinned. */}
                <div
                  ref={searchRestRef}
                  aria-hidden
                  className="pointer-events-none absolute inset-x-0 top-2 h-px sm:top-3"
                />
                {/* Above the results, not in the rail: it is the only control
                    that takes the reader's own words, and the count it moves
                    sits one line below it. Sticky, because the list pages
                    itself in as the reader scrolls and a refinement should
                    not cost a scroll back to the top. The edge appears only
                    while pinned, as a shadow so it takes no layout. */}
                <div
                  className={cn(
                    "bg-paper sticky top-0 z-10 -my-3 py-3 transition-shadow duration-150 motion-reduce:transition-none",
                    searchStuck && "shadow-[0_1px_0_var(--color-line)]",
                  )}
                >
                  <CatalogSearch value={state.q} onCommit={(q) => change({ q })} />
                </div>

                {papers.isError ? (
                  <p className="text-ink-2 py-16 text-center text-[13.5px]">
                    Could not reach the catalog. The API may still be starting up.
                  </p>
                ) : (
                  <CatalogResults
                    papers={rows}
                    total={total}
                    state={state}
                    topic={
                      facets?.categories.find((bucket) => bucket.value === state.category)?.name ??
                      null
                    }
                    loading={papers.isPending}
                    page={papers}
                    scrollElement={canvas}
                    readerHref={readerHref}
                    rememberAs={view}
                    heading={heading}
                  />
                )}
              </div>
            </main>
          )}
        </div>

        {aside}
      </div>

      {/* Outside the canvas: the list has no bottom until the last page
          loads, so a footer after it would be one the reader chases and
          never reaches, and the arXiv attribution in it is not optional
          (§6b). */}
      <SiteFooter />
    </div>
  );
}
