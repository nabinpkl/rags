import { Library, Link2, Network, ScrollText } from "lucide-react";

import type { LandingResponse } from "@/lib/api-client";

/** The four numbers the front door opens with, and the sentence that says what
 * they are. Every one is counted from the citation graph — none is configured,
 * so none can drift from what the page below it shows.
 *
 * Each icon names the KIND of thing being counted (documents, parsed lists,
 * edges, nodes), which is what tells four adjacent six-figure numbers apart at
 * a glance. */
export function HeroStats({ stats }: { stats: LandingResponse["stats"] }) {
  const facts = [
    { value: stats.papers_in_window, label: "cs papers in the window", icon: Library },
    { value: stats.papers_with_references, label: "with a parsed reference list", icon: ScrollText },
    { value: stats.citations, label: "arXiv citations extracted", icon: Link2 },
    { value: stats.cited_works, label: "distinct works cited", icon: Network },
  ];

  return (
    <section className="border-line border-b px-6 py-12 sm:py-14">
      <div className="mx-auto max-w-5xl">
        <h1 className="font-serif text-ink max-w-[19ch] text-[clamp(1.9rem,6vw,2.5rem)] leading-[1.14] font-bold">
          What is computer science building on right now?
        </h1>
        <p className="text-muted mt-4 max-w-[62ch] text-base sm:text-[16.5px]">
          We pulled every cs paper arXiv posted in {formatWindow(stats)}, extracted the reference
          list from each one, and counted. No topic modelling, no clustering, no LLM judgement —{" "}
          <b className="text-ink font-semibold">just what recent work actually cites</b>. Every
          number below opens the papers behind it.
        </p>
        <dl className="border-line bg-panel mt-6 grid grid-cols-2 overflow-hidden rounded border md:grid-cols-4">
          {facts.map((fact, i) => (
            <div
              key={fact.label}
              className={`border-line px-4 py-3 ${i % 2 === 0 ? "border-r" : ""} ${i < 2 ? "border-b md:border-b-0" : ""} md:border-r md:last:border-r-0`}
            >
              <dt className="text-muted flex items-center gap-1.5 text-[11.5px]">
                <fact.icon className="text-chart-1 size-[13px] shrink-0" aria-hidden />
                {fact.label}
              </dt>
              <dd className="font-mono text-ink mt-1.5 text-2xl font-semibold tabular-nums">
                {fact.value.toLocaleString()}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

/** "November 2007 and September 2026" from the id-months the API derived
 * from the data. An arXiv id-month is YYMM, so this needs no date parsing
 * and cannot disagree with the corpus it describes. Each side carries its
 * OWN year: the window spans decades (oldest cohorts reach 2007), and
 * pinning the start month to the end year once printed "November 2026"
 * for a window that began in November 2007. */
function formatWindow(stats: LandingResponse["stats"]): string {
  const { window_start: start, window_end: end } = stats;
  if (!start || !end) return "the indexed window";
  const fmt = (yymm: string) =>
    `${new Date(Date.UTC(2000 + Number(yymm.slice(0, 2)), Number(yymm.slice(2)) - 1, 1)).toLocaleString("en-US", { month: "long", timeZone: "UTC" })} 20${yymm.slice(0, 2)}`;
  return start === end ? fmt(end) : `${fmt(start)} and ${fmt(end)}`;
}
