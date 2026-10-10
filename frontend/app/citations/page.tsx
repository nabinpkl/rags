"use client";

import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { CitationAge } from "@/components/landing/citation-age";
import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { FoundationDetail } from "@/components/landing/foundation-detail";
import { FoundationsTable } from "@/components/landing/foundations-table";
import { Hero } from "@/components/landing/hero";
import { MethodsNote } from "@/components/landing/methods-note";
import { RecentUptake } from "@/components/landing/recent-uptake";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { agentEnabled } from "@/lib/agent-flag";
import { type Foundation, fetchLanding, fetchUptake } from "@/lib/api-client";
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
  // Fetched apart from the ranking: a slow uptake query must not hold it up,
  // and a failed one must not take the page down with it.
  const { data: uptake } = useQuery({ queryKey: ["uptake"], queryFn: fetchUptake });

  function backToCitations() {
    setSelected(null);
    setAsking(null);
    canvasRef.current?.scrollTo({ top: 0 });
  }

  return (
    <DashboardShell
      current="citations"
      canvasRef={canvasRef}
      trail={
        selected ? (
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
        )
      }
    >
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
            onBack={backToCitations}
            onAsk={agentEnabled() ? ask : undefined}
          />
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

          {/* What the newest complete month picked up, beside how far back
              the citations reach: the ranking's recent edge and its depth. */}
          {/* `items-start`: the chart sizes to its own track rather than
              stretching to the list's height beside it. */}
          <div className="grid items-start gap-4 xl:grid-cols-2">
            {uptake && <RecentUptake uptake={uptake} onSelect={openFoundation} />}
            <CitationAge stats={data.stats} citedYears={data.cited_years} />
          </div>

          <MethodsNote stats={data.stats} />
        </>
      )}
    </DashboardShell>
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
