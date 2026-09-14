import { FlaskConical, History } from "lucide-react";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { LandingResponse } from "@/lib/api-client";

/** How the numbers are made, and what they are not.
 *
 * The "what this is not" paragraph is load-bearing, not a disclaimer: it is
 * the reason the page has no theme cards. Delete it and the design looks
 * arbitrary instead of deliberate.
 */
export function MethodsNote({
  stats,
  citedYears,
}: {
  stats: LandingResponse["stats"];
  citedYears: LandingResponse["cited_years"];
}) {
  const parseRate = stats.papers_in_window
    ? Math.round((stats.papers_with_references / stats.papers_in_window) * 100)
    : 0;
  // An empty graph is a real state (a corpus built before extract_citations
  // ran). Keep the raw total to detect it, and guard the divisor separately —
  // "0% of these citations" reads as a finding when it is an absence.
  const placeable = citedYears.reduce((sum, bucket) => sum + bucket.citations, 0);
  const total = placeable || 1;
  // Only the recent tail is legible as bars; the long pre-2020 tail collapses
  // into the sentence below.
  const recent = citedYears.filter((bucket) => bucket.year !== null && bucket.year >= 2020);
  const max = Math.max(...recent.map((bucket) => bucket.citations), 1);
  // The claim worth making is against the WINDOW's own year, not a round
  // number: 82% of this cohort's citations point at work published before the
  // year the cohort itself was written in. Undated works count as older.
  const windowYear = stats.window_end ? 2000 + Number(stats.window_end.slice(0, 2)) : null;
  const beforeWindowYear = windowYear
    ? citedYears
        .filter((bucket) => bucket.year === null || bucket.year < windowYear)
        .reduce((sum, bucket) => sum + bucket.citations, 0)
    : 0;

  const steps = [
    {
      title: "1 · collect",
      body: `Every cs paper in the window's id-months, mirrored from Google's arXiv bucket. ${stats.papers_in_window.toLocaleString()} PDFs, text extracted locally, PDFs discarded.`,
    },
    {
      title: "2 · parse",
      body: `arXiv ids pulled out of each reference list by pattern. ${stats.papers_with_references.toLocaleString()} of ${stats.papers_in_window.toLocaleString()} papers yielded a usable list — ${parseRate}%.`,
    },
    {
      title: "3 · count",
      body: "One citation per (paper, target) pair. Self-citations dropped. The rank is a count; there is nothing else in it.",
    },
    {
      title: "4 · index",
      body: "The works on this page are the ones the agent can read. The page defines what is indexed, not the other way round.",
    },
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <DashboardPanel
        icon={History}
        title="How far back it reaches"
        meta={placeable ? "2020 onward" : undefined}
        className="lg:col-span-2"
      >
        <div className="flex min-h-[132px] flex-1 items-end gap-1.5" aria-hidden>
          {recent.map((bucket) => (
            <div key={bucket.year} className="flex h-full flex-1 flex-col items-center gap-1">
              <span className="text-muted font-mono text-[10px] tabular-nums">
                {Math.round((bucket.citations / total) * 100)}%
              </span>
              {/* Percentage of the track, like the trends panel, so this card
                  fills whatever height the row hands it instead of ending in
                  a band of empty panel beside a taller neighbour. */}
              <div className="relative w-full flex-1">
                <div
                  className="bg-chart-1 absolute inset-x-0 bottom-0 rounded-t-sm"
                  style={{ height: `${Math.max((bucket.citations / max) * 100, 1.5)}%` }}
                />
              </div>
              <span className="text-muted font-mono text-[10px]">{bucket.year}</span>
            </div>
          ))}
        </div>
        <p className="text-muted mt-3 text-[13px] leading-relaxed">
          {windowYear && placeable ? (
            <>
              {Math.round((beforeWindowYear / total) * 100)}% of these citations point at work
              published before {windowYear}. The newest work is not built only on the newest work,
              which is why a two-month window can say something about more than two months.
            </>
          ) : (
            "No citations to place in time yet."
          )}
        </p>
      </DashboardPanel>

      <DashboardPanel
        icon={FlaskConical}
        title="How these numbers are made"
        meta="four steps"
        className="lg:col-span-3"
      >
        <div className="mb-4 grid gap-4 sm:grid-cols-2">
          {steps.map((step) => (
            <div key={step.title}>
              <b className="text-muted mb-1 block font-mono text-[10.5px] font-semibold tracking-[0.1em] uppercase">
                {step.title}
              </b>
              <p className="text-ink m-0 text-[13px] leading-relaxed">{step.body}</p>
            </div>
          ))}
        </div>

        <div className="bg-paper border-l-rust mt-auto border-l-[3px] px-3.5 py-2.5 text-[13px] leading-relaxed">
          <b className="text-rust">What this is not.</b> It is not a citation count — it is a count
          within one window of arXiv cs, so it measures what is being built on <i>now</i>, not what
          is important overall. Papers whose reference lists did not parse ({100 - parseRate}%) are
          missing entirely. Grouping papers into named themes is deliberately absent: on this data,
          two runs of the same clustering agree on only 43–61% of pairs, so any theme label would be
          a claim about our code rather than about the literature.
        </div>
      </DashboardPanel>
    </div>
  );
}
