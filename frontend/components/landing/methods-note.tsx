import { ChevronRight } from "lucide-react";

import type { LandingResponse } from "@/lib/api-client";

/** How the numbers are made, and what they are not, folded shut.
 *
 * The "not a census, no themes" line is load-bearing: it is the reason the
 * page has no theme cards. It stays on the page, one click deep, because the
 * page reads without it and a reader who doubts a number knows where to look.
 */
export function MethodsNote({ stats }: { stats: LandingResponse["stats"] }) {
  // Over papers whose text reached the parser, NEVER over every catalog row:
  // that denominator printed a 30% parse rate for a parser that yields 81%.
  const parseRate = stats.papers_parsed
    ? Math.round((stats.papers_with_references / stats.papers_parsed) * 100)
    : 0;

  const steps = [
    ["Collect", "cs papers from arXiv's Google Cloud mirror, plus the older works they cite."],
    ["Parse", `arXiv ids from each reference list. ${parseRate}% of papers yield one.`],
    ["Count", "One citation per citing paper and work. Self-citations dropped."],
    ["Index", "The agent reads and quotes the recent papers that cite the works ranked here."],
  ] as const;

  return (
    <details className="group border-line bg-panel rounded-md border">
      <summary className="text-ink hover:bg-panel-hover flex cursor-pointer list-none items-center gap-2 rounded-md px-4 py-3 text-[13px] font-medium transition-colors motion-reduce:transition-none [&::-webkit-details-marker]:hidden">
        <ChevronRight
          className="text-muted size-4 shrink-0 transition-transform group-open:rotate-90 motion-reduce:transition-none"
          aria-hidden
        />
        How this is counted
      </summary>
      <div className="border-line grid gap-x-8 gap-y-3 border-t px-4 py-4 sm:grid-cols-2">
        {steps.map(([title, body]) => (
          <p key={title} className="text-ink max-w-[60ch] text-[13px] leading-relaxed">
            <b className="font-semibold">{title}.</b> {body}
          </p>
        ))}
        <p className="text-ink-2 max-w-[60ch] text-[13px] leading-relaxed sm:col-span-2">
          A count over a sample of recent arXiv cs, not a measure of importance. No topic labels:
          two runs of the same clustering agree on only 43–61% of pairs.
        </p>
      </div>
    </details>
  );
}
