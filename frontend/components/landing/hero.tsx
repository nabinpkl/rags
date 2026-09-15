import type { LandingResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** The page's opening claim, in one sentence, and then out of the way.
 *
 * It carried four KPI cards (papers, citations, cited works, indexed papers).
 * Four six-figure numbers at the top of a page about what CS is building on
 * read as the finding, when the finding is the ranked list below: the totals
 * only describe the pile the list was counted from. The two a reader needs to
 * size that pile stay, as prose, inside the sentence that already explains
 * what they are. The rest live where they are used — the cited-works total in
 * the table's own footer, the indexed count in step 4 of the method note.
 */
export function Hero({ stats }: { stats: LandingResponse["stats"] }) {
  return (
    <div>
      <h1 className="font-serif text-ink max-w-[30ch] text-[clamp(1.55rem,3.2vw,2rem)] leading-[1.16] font-bold">
        What is computer science building on right now?
      </h1>
      <p className="text-muted mt-3 max-w-[68ch] text-[14.5px] leading-relaxed">
        We pulled <b className="text-ink font-semibold">{sample(stats)}</b> arXiv posted{" "}
        {formatCohort(stats)}, extracted the reference list from each one, and counted{" "}
        <b className="text-ink font-semibold">
          {stats.citations.toLocaleString()} citations to other arXiv papers
        </b>
        . No topic modelling, no clustering, no LLM judgement, just what recent work actually cites.
        Every number below opens the papers behind it.
      </p>
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
