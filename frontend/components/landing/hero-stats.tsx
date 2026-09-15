import { BookOpen, Library, Link2, Network } from "lucide-react";

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
  // Four numbers a reader can use: how much of arXiv this counted, what came
  // out of it, and what they can ask about. "Papers with a parsed reference
  // list" used to sit in slot two, which is a stage count of our pipeline —
  // true, and of no use to anyone reading the page. Its one reader-facing
  // consequence, that the counts undercount, is a rate, and lives in the
  // methods note as one.
  const facts = [
    { value: stats.cohort_papers, label: cohortLabel(stats), icon: Library },
    { value: stats.citations, label: "arXiv citations counted in them", icon: Link2 },
    { value: stats.cited_works, label: "distinct works they cite", icon: Network },
    { value: stats.readable_papers, label: "papers the agent reads and quotes", icon: BookOpen },
  ];

  return (
    <div>
      <h1 className="font-serif text-ink max-w-[30ch] text-[clamp(1.55rem,3.2vw,2rem)] leading-[1.16] font-bold">
        What is computer science building on right now?
      </h1>
      <p className="text-muted mt-3 max-w-[68ch] text-[14.5px] leading-relaxed">
        We pulled <b className="text-ink font-semibold">{sample(stats)}</b> arXiv posted{" "}
        {formatCohort(stats)}, extracted the reference list from each one, and counted. No topic
        modelling, no clustering, no LLM judgement, just what recent work actually cites. Every
        number below opens the papers behind it.
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

/** The whole prepositional phrase, because the preposition depends on the
 * span: "in August 2026" for one month, "between July 2026 and September
 * 2026" for several. A fixed "in" in the sentence read "in between".
 *
 * Each side carries its OWN year: pinning the start month to the end year
 * once printed "November 2026" for a span beginning in November 2007. And
 * "between", not "and": the cohort spans three months today, where "July and
 * September" would name two and skip the largest one. */
function formatCohort(stats: LandingResponse["stats"]): string {
  const { cohort_start: start, cohort_end: end } = stats;
  if (!start || !end) return "in the indexed months";
  if (start === end) return `in ${formatIdMonth(end)}`;
  return `between ${formatIdMonth(start)} and ${formatIdMonth(end)}`;
}

/** The sentence's subject, and the page's central claim about itself.
 *
 * It said "every cs paper arXiv posted in ...", which was measured false:
 * 94% of July 2026, 49% of August, 5% of September. So the claim is now the
 * measured one, with the catalog's own count in it, and it degrades to the
 * bare number when the snapshot is too old to supply a denominator rather
 * than falling back to the word it cannot support.
 */
function sample(stats: LandingResponse["stats"]): string {
  const held = stats.cohort_papers.toLocaleString();
  const total = stats.cohort_catalog_papers;
  if (!total) return `${held} cs papers`;
  return `${held} of the ${total.toLocaleString()} cs papers`;
}

/** The KPI label carries the same denominator the sentence does, because a
 * six-figure number under "cs papers" is read as the field's output. The
 * share is spelled out rather than left to be divided: "of 32,519" is a
 * denominator, "60% of what arXiv posted" is the fact taken away from it. */
function cohortLabel(stats: LandingResponse["stats"]): string {
  const total = stats.cohort_catalog_papers;
  if (!total) return "cs papers in the cohort months";
  const share = Math.round((stats.cohort_papers / total) * 100);
  return `${share}% of the ${total.toLocaleString()} cs papers arXiv posted then`;
}
