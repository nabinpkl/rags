"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { FoundationDetail } from "@/components/landing/foundation-detail";
import { FoundationsTable } from "@/components/landing/foundations-table";
import { HeroStats } from "@/components/landing/hero-stats";
import { LatestPapers } from "@/components/landing/latest-papers";
import { MethodsNote } from "@/components/landing/methods-note";
import { TrendsChart } from "@/components/landing/trends-chart";
import { SiteFooter } from "@/components/site-footer";
import { type Foundation, fetchLanding, fetchLatest, fetchTrends } from "@/lib/api-client";
import { useAgentSessionStore } from "@/stores/agent-session-store";

/** The front door (§4c decision 2 amendment: a second STATIC route, still no
 * dynamic ones — the app shell moved to `/app` and is unchanged).
 *
 * A visitor understands what this is without typing a character: the page
 * opens with counted citations, every number opens the papers behind it, and
 * the agent is entered FROM a claim rather than from a blank prompt. That
 * ordering is the whole product argument — the page tells you *that* 1,174
 * papers cite Qwen3; only reading them tells you *what for*.
 */
export default function LandingPage() {
  const [selected, setSelected] = useState<Foundation | null>(null);
  const [asking, setAsking] = useState<Foundation | null>(null);
  const resetSession = useAgentSessionStore((state) => state.reset);

  // A conversation belongs to the claim it was started from. The SERVER
  // already refuses to carry history across a scope change
  // (session_store.get_or_create) — this clears the VISIBLE transcript to
  // match, so the panel never shows answers about one foundation under
  // another one's heading.
  function ask(foundation: Foundation) {
    if (asking?.arxiv_id !== foundation.arxiv_id) resetSession();
    setAsking(foundation);
  }

  const { data, isPending, isError } = useQuery({
    queryKey: ["landing"],
    queryFn: () => fetchLanding({ limit: 40 }),
  });
  // Dashboard sections fetch independently: a slow chart must not hold up
  // the ranking, and a failed chart must not take the page down with it.
  const { data: latest } = useQuery({
    queryKey: ["latest"],
    queryFn: () => fetchLatest({ limit: 8 }),
  });
  const { data: trends } = useQuery({ queryKey: ["trends"], queryFn: fetchTrends });

  return (
    <div className="bg-paper text-ink flex min-h-dvh flex-col">
      <header className="bg-panel border-line sticky top-0 z-10 border-b">
        <div className="mx-auto flex h-[54px] max-w-5xl items-center gap-4 px-6">
          <span className="flex items-baseline gap-2">
            <b className="font-serif text-[22px] font-bold">
              ask<em className="text-teal-ink not-italic">RAG</em>
            </b>
            <span className="text-muted font-mono text-[10.5px] tracking-wider">
              arXiv cs · rolling window
            </span>
          </span>
          {!selected && data && (
            <nav
              aria-label="Dashboard sections"
              className="text-muted hidden items-center gap-4 font-mono text-[11px] sm:flex"
            >
              <a href="#ranking" className="hover:text-ink">
                ranking
              </a>
              <a href="#trends" className="hover:text-ink">
                trends
              </a>
              <a href="#latest" className="hover:text-ink">
                latest
              </a>
              <a href="#methods" className="hover:text-ink">
                methods
              </a>
            </nav>
          )}
          <Link
            href="/app"
            className="border-line text-muted hover:text-ink focus-visible:outline-teal ml-auto rounded-[3px] border px-2.5 py-1 font-mono text-[11px] focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            browse the corpus →
          </Link>
        </div>
      </header>

      <main className="flex-1">
        {isPending && <p className="text-muted mx-auto max-w-5xl px-6 py-16">Loading…</p>}
        {isError && (
          <p className="text-muted mx-auto max-w-5xl px-6 py-16">
            Could not reach the corpus. The API may still be starting up.
          </p>
        )}

        {data && (
          <>
            {!selected && <HeroStats stats={data.stats} />}

            {selected ? (
              <FoundationDetail
                foundation={selected}
                onBack={() => {
                  setSelected(null);
                  setAsking(null);
                }}
                onAsk={ask}
              />
            ) : (
              <FoundationsTable
                stats={data.stats}
                foundations={data.foundations}
                onSelect={(foundation) => {
                  setSelected(foundation);
                  setAsking(null);
                }}
              />
            )}

            {asking && (
              <section className="border-line bg-panel border-t px-6 py-8">
                <div className="mx-auto max-w-5xl">
                  <h2 className="font-serif text-ink mb-1 text-2xl font-semibold">
                    Ask about these papers
                  </h2>
                  <p className="text-muted mb-4 max-w-[70ch] text-sm">
                    The agent reads them with tools — search, fetch, quote — rather than being
                    handed a wall of context. It answers only from what it can cite, and quotes are
                    capped at 50 words, 3 per paper.
                  </p>
                  <div className="border-machine-line h-[520px] overflow-hidden rounded border">
                    <ChatPanel
                      scope={{
                        foundationId: asking.arxiv_id,
                        label: `the papers we indexed that cite “${asking.title ?? asking.arxiv_id}”`,
                        starters: starterQuestions(asking),
                      }}
                    />
                  </div>
                </div>
              </section>
            )}

            {!selected && (trends || latest) && (
              <section aria-label="Overview" className="border-line border-t px-6 py-8">
                <div className="mx-auto grid max-w-5xl items-start gap-6 lg:grid-cols-5">
                  {trends && (
                    <div className="lg:col-span-3">
                      <TrendsChart months={trends.months} />
                    </div>
                  )}
                  {latest && (
                    <div className="lg:col-span-2">
                      <LatestPapers papers={latest.papers} />
                    </div>
                  )}
                </div>
              </section>
            )}
            {!selected && <MethodsNote stats={data.stats} citedYears={data.cited_years} />}
          </>
        )}
      </main>

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
