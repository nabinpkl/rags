import { Library, Link2, Network, ScrollText } from "lucide-react";

import type { LandingResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** The overview band: what the page claims, and the four numbers it claims it
 * with. Every one is counted from the citation graph — none is configured, so
 * none can drift from what the panels below it show.
 *
 * The cards put the VALUE above its label because a reader scanning a KPI row
 * is looking for magnitudes first and only reads the label of the one that
 * surprised them. The DOM keeps label-then-value (`flex-col-reverse` does the
 * visual swap), which is the order a screen reader should hear it in.
 *
 * Each glyph names the KIND of thing counted (documents, parsed lists, edges,
 * nodes) — that is what tells four adjacent six-figure numbers apart.
 */
export function HeroStats({ stats }: { stats: LandingResponse["stats"] }) {
  const facts = [
    { value: stats.papers_in_window, label: "cs papers in the window", icon: Library },
    {
      value: stats.papers_with_references,
      label: "with a parsed reference list",
      icon: ScrollText,
    },
    { value: stats.citations, label: "arXiv citations extracted", icon: Link2 },
    { value: stats.cited_works, label: "distinct works cited", icon: Network },
  ];

  return (
    <div>
      <h1 className="font-serif text-ink max-w-[30ch] text-[clamp(1.55rem,3.2vw,2rem)] leading-[1.16] font-bold">
        What is computer science building on right now?
      </h1>
      <p className="text-muted mt-3 max-w-[68ch] text-[14.5px] leading-relaxed">
        We pulled every cs paper arXiv posted in {formatWindow(stats)}, extracted the reference list
        from each one, and counted. No topic modelling, no clustering, no LLM judgement —{" "}
        <b className="text-ink font-semibold">just what recent work actually cites</b>. Every number
        below opens the papers behind it.
      </p>

      <dl className="mt-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
        {facts.map((fact) => (
          <div key={fact.label} className="bg-panel border-line rounded-md border p-4">
            <span
              className="bg-teal-soft text-teal-ink grid size-8 place-items-center rounded"
              aria-hidden
            >
              <fact.icon className="size-4" />
            </span>
            <div className="mt-3.5 flex flex-col-reverse">
              <dt className="text-muted mt-1.5 text-[12px] leading-snug">{fact.label}</dt>
              <dd className="font-mono text-ink text-[clamp(1.35rem,2.6vw,1.7rem)] leading-none font-semibold tabular-nums">
                {fact.value.toLocaleString()}
              </dd>
            </div>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** "November 2007 and September 2026" from the id-months the API derived from
 * the data. Each side carries its OWN year: the window spans decades (oldest
 * cohorts reach 2007), and pinning the start month to the end year once
 * printed "November 2026" for a window that began in November 2007. */
function formatWindow(stats: LandingResponse["stats"]): string {
  const { window_start: start, window_end: end } = stats;
  if (!start || !end) return "the indexed window";
  return start === end ? formatIdMonth(end) : `${formatIdMonth(start)} and ${formatIdMonth(end)}`;
}
