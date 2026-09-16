"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Menu, MessagesSquare } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { SECTIONS, SECTION_IDS, DashboardSidebar } from "@/components/landing/dashboard-sidebar";
import { FoundationDetail } from "@/components/landing/foundation-detail";
import { CategoryCensus } from "@/components/landing/category-census";
import { FoundationsTable } from "@/components/landing/foundations-table";
import { Hero } from "@/components/landing/hero";
import { HoldingsChart } from "@/components/landing/holdings-chart";
import { LatestPapers } from "@/components/landing/latest-papers";
import { MethodsNote } from "@/components/landing/methods-note";
import { RecentUptake } from "@/components/landing/recent-uptake";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { SiteFooter } from "@/components/site-footer";
import { useActiveSection } from "@/hooks/use-active-section";
import {
  type Foundation,
  fetchCategoryCensus,
  fetchCoverage,
  fetchLanding,
  fetchLatest,
  fetchUptake,
} from "@/lib/api-client";
import { formatIdMonthRange } from "@/lib/id-month";
import { useAgentSessionStore } from "@/stores/agent-session-store";

/** The front door (§4c decision 2 amendment: a second STATIC route, still no
 * dynamic ones — the app shell moved to `/app` and is unchanged).
 *
 * A visitor understands what this is without typing a character: the canvas
 * opens with counted citations, every number opens the papers behind it, and
 * the agent is entered FROM a claim rather than from a blank prompt. That
 * ordering is the whole product argument — the page tells you *that* 1,174
 * papers cite Qwen3; only reading them tells you *what for*.
 *
 * Shape is an app shell, not a scrolling document: a rail that says where you
 * are, a bar that says what you are looking at, and a canvas of identically
 * framed panels. The rail's docking rule is the shell rule the rest of the
 * app already follows (`.claude/rules/frontend.md`) — viewport width decides
 * dock-vs-drawer, so this reuses `DrawerPanel` rather than growing a second
 * implementation of the same behaviour.
 */
export default function LandingPage() {
  const [selected, setSelected] = useState<Foundation | null>(null);
  const [asking, setAsking] = useState<Foundation | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const pendingScroll = useRef<string | null>(null);
  const canvasRef = useRef<HTMLElement>(null);
  const resetSession = useAgentSessionStore((state) => state.reset);

  // A conversation belongs to the claim it was started from. The SERVER
  // already refuses to carry history across a scope change
  // (session_store.get_or_create) — this clears the VISIBLE transcript to
  // match, so the panel never shows answers about one foundation under
  // another one's heading.
  // Two panels open a foundation now (the ranking and the uptake list), so
  // the transition lives once: the detail replaces the bands, and a canvas
  // still scrolled to the activity band would otherwise open it mid-page.
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
    queryFn: () => fetchLatest({ limit: 6 }),
  });
  const { data: coverage } = useQuery({ queryKey: ["coverage"], queryFn: fetchCoverage });
  const { data: uptake } = useQuery({ queryKey: ["uptake"], queryFn: fetchUptake });
  const { data: census } = useQuery({ queryKey: ["census"], queryFn: fetchCategoryCensus });

  const showingBands = Boolean(data) && selected === null;
  const active = useActiveSection(SECTION_IDS, canvasRef, showingBands);

  // A rail click while a foundation's detail is open has no target yet: the
  // bands are unmounted, so `getElementById` in this handler would find
  // nothing. The id is parked on a ref and the scroll runs on the commit that
  // brings the bands back — a ref rather than state because the effect must
  // not queue a render of its own (react-hooks/set-state-in-effect).
  function goToSection(id: string) {
    setNavOpen(false);
    if (showingBands) {
      scrollToSection(id);
      return;
    }
    pendingScroll.current = id;
    setSelected(null);
    setAsking(null);
  }

  useEffect(() => {
    if (!showingBands || !pendingScroll.current) return;
    const id = pendingScroll.current;
    pendingScroll.current = null;
    scrollToSection(id);
  }, [showingBands]);

  const cohortLabel = data
    ? formatIdMonthRange(data.stats.cohort_start, data.stats.cohort_end)
    : null;
  const activeLabel = SECTIONS.find((section) => section.id === active)?.label ?? "Overview";

  return (
    <div className="bg-paper text-ink flex h-dvh flex-col">
      <div className="flex min-h-0 flex-1">
        <DrawerPanel
          dockAt="lg"
          side="left"
          label="Dashboard navigation"
          open={navOpen}
          onClose={() => setNavOpen(false)}
          className="bg-panel border-line w-[248px] shrink-0 border-r"
        >
          {/* A foundation's detail belongs to the Foundations band, so the
              rail says so rather than leaving the last scrolled band lit
              under a canvas that no longer shows it. */}
          <DashboardSidebar
            active={selected ? "foundations" : active}
            cohortLabel={cohortLabel}
            onNavigate={goToSection}
          />
        </DrawerPanel>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="bg-panel border-line flex h-[57px] shrink-0 items-center gap-3 border-b px-4">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
              aria-expanded={navOpen}
              className="border-line text-ink hover:bg-paper -ml-1 flex size-9 shrink-0 items-center justify-center rounded border transition-colors motion-reduce:transition-none lg:hidden"
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
                        onClick={() => goToSection("foundations")}
                        className="text-muted hover:text-ink transition-colors motion-reduce:transition-none"
                      >
                        Foundations
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
                  <li className="text-ink font-medium">{activeLabel}</li>
                )}
              </ol>
            </nav>

            <Link
              href="/app"
              className="bg-teal-deep hover:bg-teal-deep-hover flex shrink-0 items-center gap-1.5 rounded px-3 py-1.5 text-[12.5px] font-medium text-white transition-colors motion-reduce:transition-none"
            >
              Browse the corpus
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </header>

          {/* `relative` is load-bearing, not decoration: `sr-only` is
              `position: absolute`, so a screen-reader summary anywhere on the
              canvas takes the INITIAL containing block as its own unless
              something here is positioned — and an abspos box outside the
              scroller's containing block is not clipped by it. Two chart
              summaries were enough to give the document 580px of phantom
              scroll, which the browser then used on every anchor jump,
              scrolling the top bar and the rail out of view. */}
          <main
            ref={canvasRef}
            className="relative min-h-0 flex-1 overflow-y-auto scroll-smooth motion-reduce:scroll-auto"
          >
            <div className="mx-auto flex max-w-[1280px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-6">
              {isPending && <p className="text-muted py-16 text-center">Loading the corpus…</p>}
              {isError && (
                <p className="text-muted py-16 text-center">
                  Could not reach the corpus. The API may still be starting up.
                </p>
              )}

              {data && selected && (
                <>
                  <FoundationDetail
                    foundation={selected}
                    onBack={() => {
                      setSelected(null);
                      setAsking(null);
                    }}
                    onAsk={ask}
                  />
                  {asking && (
                    <DashboardPanel
                      icon={MessagesSquare}
                      title="Ask about these papers"
                      meta="scoped"
                      description="The agent reads them with tools (search, fetch, quote) rather than being handed a wall of context. It answers only from what it can cite, and quotes are capped at 50 words, 3 per paper."
                      bodyClassName="p-0"
                    >
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
                  <section id="overview" className="scroll-mt-5">
                    <Hero stats={data.stats} />
                  </section>

                  <section id="foundations" className="scroll-mt-5">
                    <FoundationsTable
                      stats={data.stats}
                      foundations={data.foundations}
                      onSelect={openFoundation}
                    />
                  </section>

                  {/* The activity band is the page's "right now": what
                      arrived, what the newest complete month picked up, and
                      what the field posted while that happened. All three
                      are counts over months we hold whole, which is what
                      separates them from a chart of our download schedule. */}
                  <section id="activity" className="flex scroll-mt-5 flex-col gap-4">
                    <div className="grid gap-4 xl:grid-cols-2">
                      {latest && <LatestPapers papers={latest.papers} />}
                      {uptake && <RecentUptake uptake={uptake} onSelect={openFoundation} />}
                    </div>
                    {census && <CategoryCensus census={census} />}
                  </section>

                  {/* Provenance sits in the method band, last, deliberately.
                      As the activity band's widest panel it read as a
                      finding: bars of papers-per-month with no denominator,
                      on a page about what CS is building on, invited "19
                      papers in October 2025" as a fact about October rather
                      than about our download schedule. */}
                  <section id="methods" className="flex scroll-mt-5 flex-col gap-4">
                    <MethodsNote stats={data.stats} citedYears={data.cited_years} />
                    {coverage && <HoldingsChart months={coverage.months} />}
                  </section>
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

/** Scrolls a band to the top of the canvas, honouring the reduced-motion
 * preference the base layer already honours everywhere else. */
function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    block: "start",
  });
}
