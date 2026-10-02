"use client";

import { useQuery } from "@tanstack/react-query";
import { Menu } from "lucide-react";
import { useRef, useState } from "react";

import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { CitationAge } from "@/components/landing/citation-age";
import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { FoundationDetail } from "@/components/landing/foundation-detail";
import { CategoryCensus } from "@/components/landing/category-census";
import { FoundationsTable } from "@/components/landing/foundations-table";
import { Hero } from "@/components/landing/hero";
import { LatestPapers } from "@/components/landing/latest-papers";
import { MethodsNote } from "@/components/landing/methods-note";
import { RecentUptake } from "@/components/landing/recent-uptake";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { ShellSidebar } from "@/components/shell/shell-sidebar";
import { SiteFooter } from "@/components/site-footer";
import {
  type Foundation,
  fetchCategoryCensus,
  fetchLanding,
  fetchLatest,
  fetchUptake,
} from "@/lib/api-client";
import { useAgentSessionStore } from "@/stores/agent-session-store";

/** What recent cs is building on, counted from reference lists. A STATIC
 * route (§4c decision 2, amended 2026-10-02: Explore is the home page).
 *
 * Every number opens the papers behind it, and the agent is entered FROM a
 * claim rather than from a blank prompt: the page tells you *that* 1,859
 * papers cite Qwen3; only reading them tells you *what for*.
 *
 * Shape is an app shell, not a scrolling document: the rail (`ShellSidebar`,
 * shared with the catalog) says which view, the bar says what you are
 * looking at, and the canvas holds identically framed panels.
 */
export default function CitationsPage() {
  const [selected, setSelected] = useState<Foundation | null>(null);
  const [asking, setAsking] = useState<Foundation | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const canvasRef = useRef<HTMLElement>(null);
  const resetSession = useAgentSessionStore((state) => state.reset);

  // A conversation belongs to the claim it was started from. The SERVER
  // already refuses to carry history across a scope change
  // (session_store.get_or_create) — this clears the VISIBLE transcript to
  // match, so the panel never shows answers about one foundation under
  // another one's heading.
  // Two panels open a foundation now (the ranking and the uptake list), so
  // the transition lives once: the detail replaces the ranking, and a canvas
  // still scrolled down its panels would otherwise open it mid-page.
  function openFoundation(foundation: Foundation) {
    setSelected(foundation);
    setAsking(null);
    canvasRef.current?.scrollTo({ top: 0 });
  }

  function ask(foundation: Foundation) {
    if (asking?.arxiv_id !== foundation.arxiv_id) resetSession();
    setAsking(foundation);
  }

  const { data, isPending, isError } = useQuery({
    queryKey: ["landing"],
    queryFn: () => fetchLanding({ limit: 40 }),
  });
  // Panels fetch independently: a slow chart must not hold up the ranking,
  // and a failed chart must not take the dashboard down with it.
  const { data: latest } = useQuery({
    queryKey: ["latest"],
    queryFn: () => fetchLatest({ limit: 8 }),
  });
  const { data: uptake } = useQuery({ queryKey: ["uptake"], queryFn: fetchUptake });
  const { data: census } = useQuery({ queryKey: ["census"], queryFn: fetchCategoryCensus });

  function backToCitations() {
    setSelected(null);
    setAsking(null);
    canvasRef.current?.scrollTo({ top: 0 });
  }

  return (
    <div className="bg-paper text-ink flex h-dvh flex-col">
      <div className="flex min-h-0 flex-1">
        {/* Same width and same breakpoint as the catalog's: one rail serving
            both views, so a reader moving between them sees the column stay
            put rather than resize under the pointer. */}
        <DrawerPanel
          dockAt="md"
          side="left"
          label="Navigation"
          open={navOpen}
          onClose={() => setNavOpen(false)}
          className="bg-panel border-line w-[min(320px,86vw)] shrink-0 border-r md:w-[264px]"
        >
          <ShellSidebar current="citations" />
        </DrawerPanel>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="bg-panel border-line flex h-[57px] shrink-0 items-center gap-3 border-b px-4">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
              aria-expanded={navOpen}
              className="border-line text-ink hover:bg-panel-hover -ml-1 flex size-9 shrink-0 items-center justify-center rounded border transition-colors motion-reduce:transition-none md:hidden"
            >
              <Menu className="size-4" aria-hidden />
            </button>

            <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
              <ol className="flex min-w-0 items-center gap-2 font-mono text-[11.5px]">
                <li className="text-muted hidden sm:block">askRAG</li>
                <li aria-hidden className="text-line hidden sm:block">
                  /
                </li>
                {selected ? (
                  <>
                    <li>
                      <button
                        type="button"
                        onClick={backToCitations}
                        className="text-muted hover:text-ink transition-colors motion-reduce:transition-none"
                      >
                        Citations
                      </button>
                    </li>
                    <li aria-hidden className="text-line">
                      /
                    </li>
                    <li className="text-ink min-w-0 truncate font-medium">
                      {selected.title ?? selected.arxiv_id}
                    </li>
                  </>
                ) : (
                  <li className="text-ink font-medium">Citations</li>
                )}
              </ol>
            </nav>
          </header>

          {/* `relative` is load-bearing, not decoration: `sr-only` is
              `position: absolute`, so a screen-reader summary anywhere on the
              canvas takes the INITIAL containing block as its own unless
              something here is positioned — and an abspos box outside the
              scroller's containing block is not clipped by it. Two chart
              summaries were enough to give the document 580px of phantom
              scroll, which the browser then used on every scroll-to-top,
              taking the top bar and the rail out of view with it. */}
          <main ref={canvasRef} className="relative min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex max-w-[1280px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-6">
              {isPending && <p className="text-muted py-16 text-center">Loading the corpus…</p>}
              {isError && (
                <p className="text-muted py-16 text-center">
                  Could not reach the corpus. The API may still be starting up.
                </p>
              )}

              {data && selected && (
                <>
                  <FoundationDetail foundation={selected} onBack={backToCitations} onAsk={ask} />
                  {asking && (
                    <DashboardPanel title="Ask about these papers" bodyClassName="p-0">
                      <div className="h-[520px] overflow-hidden rounded-b-md">
                        <ChatPanel
                          scope={{
                            foundationId: asking.arxiv_id,
                            label: `the papers we indexed that cite “${asking.title ?? asking.arxiv_id}”`,
                            starters: starterQuestions(asking),
                          }}
                        />
                      </div>
                    </DashboardPanel>
                  )}
                </>
              )}

              {data && selected === null && (
                <>
                  <Hero stats={data.stats} />

                  <FoundationsTable foundations={data.foundations} onSelect={openFoundation} />

                  {/* The page's "right now": what arrived and what the newest
                      complete month picked up. */}
                  <div className="grid gap-4 xl:grid-cols-2">
                    {latest && <LatestPapers papers={latest.papers} />}
                    {uptake && <RecentUptake uptake={uptake} onSelect={openFoundation} />}
                  </div>

                  {/* The field's shape and the cited work's age: two context
                      panels, paired so neither stretches a full row of bars. */}
                  <div className="grid gap-4 xl:grid-cols-2">
                    {census && <CategoryCensus census={census} />}
                    <CitationAge stats={data.stats} citedYears={data.cited_years} />
                  </div>

                  <MethodsNote stats={data.stats} />
                </>
              )}
            </div>
          </main>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}

/** Openers computed from the claim, never a blank prompt.
 *
 * Entry is always a claim: the reader arrives here already knowing THAT N
 * papers cite this work, and these are the questions that count answers
 * cannot reach. */
function starterQuestions(foundation: Foundation): readonly string[] {
  const name = foundation.title ?? foundation.arxiv_id;
  return [
    `What do these papers use ${name} for?`,
    `Do any of them report replacing or moving away from it?`,
    `What do they measure, and on which benchmarks?`,
  ];
}
