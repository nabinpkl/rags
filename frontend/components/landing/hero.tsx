import type { LandingResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

/** The page's name and one line of scope. Corpus totals are absent on
 * purpose: they size our pile, not the finding. How much of each month we
 * hold is stated on Explore, beside the list it scopes.
 */
export function Hero({ stats }: { stats: LandingResponse["stats"] }) {
  return (
    <div className="pt-2 pb-1">
      <h1 className="font-serif text-ink max-w-[24ch] text-[clamp(1.7rem,3.4vw,2.35rem)] leading-[1.1] font-bold text-balance">
        Citation counts
      </h1>
      <p className="text-ink-2 mt-3 max-w-[60ch] text-[15px] leading-snug">
        The arXiv work cited most by cs papers posted {formatCohort(stats)}.
      </p>
    </div>
  );
}

/** "in August 2026" for one month, "from July 2026 to September 2026" for
 * several. Each side carries its OWN year: pinning the start month to the end
 * year once printed "November 2026" for a span beginning in November 2007. */
function formatCohort(stats: LandingResponse["stats"]): string {
  const { cohort_start: start, cohort_end: end } = stats;
  if (!start || !end) return "in the indexed months";
  if (start === end) return `in ${formatIdMonth(end)}`;
  return `from ${formatIdMonth(start)} to ${formatIdMonth(end)}`;
}
