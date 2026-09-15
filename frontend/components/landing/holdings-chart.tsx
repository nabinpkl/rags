import { Layers } from "lucide-react";

import { DashboardPanel } from "@/components/landing/dashboard-panel";
import type { CoverageResponse } from "@/lib/api-client";
import { formatIdMonth } from "@/lib/id-month";

const CHART_MONTHS = 12;
/** A DEFINITE track height, not `flex-1`. The bars size themselves as a
 * percentage of their track, and a percentage of an auto-height parent is
 * zero: in the activity band the panel inherited its height from a taller
 * neighbour and the flex version worked, but standing alone in the method
 * band every bar collapsed to its 2px minimum. */
const TRACK_CLASS = "h-28";

type Month = CoverageResponse["months"][number];

/** How much of each month we actually hold. Provenance, not a finding.
 *
 * This panel used to be "The corpus, month by month" in the dashboard's
 * activity band, plotting papers-per-month with no denominator anywhere on
 * it. Nineteen papers in October 2025 then read as a fact about October,
 * when arXiv posted thousands of cs papers that month and we sampled twenty.
 * The bars encode our download schedule, so the panel says so, sits in the
 * methods band, and carries the catalog's own count for every month.
 *
 * Two rows because they answer different questions and share no scale:
 * how many papers we took, and what share of that month that was. Each row
 * prints its own peak, since a bar chart whose scale is implied is
 * decoration.
 */
export function HoldingsChart({ months }: { months: Month[] }) {
  if (months.length === 0) return null;

  const trailing = months.slice(-CHART_MONTHS);
  // Densest of the months CHARTED, not of the series: the sentence says
  // "here", and naming a month whose bar is not on screen is a small lie of
  // exactly the kind this panel exists to stop telling.
  const dense = [...trailing].sort((a, b) => share(b) - share(a))[0];

  return (
    <DashboardPanel
      icon={Layers}
      title="How much of each month we hold"
      meta={`${formatIdMonth(trailing[0].month, "short")} – ${formatIdMonth(trailing[trailing.length - 1].month, "short")}`}
      description={
        <>
          Bar height is our collection, not arXiv&rsquo;s output.{" "}
          {dense && dense.catalog_papers ? (
            <>
              The densest month here is {formatIdMonth(dense.month)}, where we hold{" "}
              {dense.papers_held.toLocaleString()} of the {dense.catalog_papers.toLocaleString()} cs
              papers arXiv posted ({Math.round(share(dense) * 100)}%).{" "}
            </>
          ) : null}
          Everything before the recent cohort is a few papers a month from an earlier sample, plus
          the older works the cohort cites: a thin month means we collected little, never that
          little was published.
        </>
      }
    >
      <div className="flex flex-col gap-6">
        <BarRow
          label="papers we hold"
          buckets={trailing}
          value={(m) => m.papers_held}
          format={(v) => v.toLocaleString()}
          colorClass="bg-chart-1"
        />
        <BarRow
          label="share of that month"
          buckets={trailing}
          value={(m) => Math.round(share(m) * 1000) / 10}
          format={(v) => `${v}%`}
          // A month the catalog snapshot cannot answer for is not 0%: it is
          // unknown, and the row says so rather than drawing a bar.
          unknown={(m) => m.catalog_papers === null}
          colorClass="bg-chart-2"
        />
      </div>
    </DashboardPanel>
  );
}

function share(month: Month): number {
  return month.catalog_papers ? month.papers_held / month.catalog_papers : 0;
}

function BarRow({
  label,
  buckets,
  value,
  format,
  colorClass,
  unknown,
}: {
  label: string;
  buckets: Month[];
  value: (m: Month) => number;
  format: (v: number) => string;
  colorClass: string;
  unknown?: (m: Month) => boolean;
}) {
  const max = Math.max(...buckets.map(value), 1);
  const peak = buckets.reduce((best, m) => (value(m) > value(best) ? m : best), buckets[0]);
  const last = buckets[buckets.length - 1];

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p className="text-ink flex items-center gap-1.5 font-mono text-[10.5px] tracking-[0.1em] uppercase">
          <span className={`${colorClass} size-2 shrink-0 rounded-[1px]`} aria-hidden />
          {label}
        </p>
        <p className="text-muted shrink-0 font-mono text-[10.5px] tabular-nums">
          peak {format(value(peak))}
        </p>
      </div>
      <div className={`border-line flex items-end gap-[3px] border-b ${TRACK_CLASS}`} aria-hidden>
        {buckets.map((m) => {
          const missing = unknown?.(m) ?? false;
          return (
            <div
              key={m.month}
              className="hover:bg-teal-soft relative h-full flex-1 rounded-t-sm transition-colors motion-reduce:transition-none"
              title={
                missing
                  ? `${formatIdMonth(m.month)}: no catalog total (the snapshot predates it)`
                  : `${formatIdMonth(m.month)}: ${format(value(m))} ${label}`
              }
            >
              {/* Bars are a PERCENTAGE of the track, not a pixel height, so the
                  card fills whatever the dashboard row hands it. A zero month
                  draws nothing: a minimum stub would render a quantity that is
                  not there. */}
              <div
                className={`${colorClass} absolute inset-x-0 bottom-0 rounded-t-sm`}
                style={{
                  height: missing || value(m) === 0 ? 0 : `${(value(m) / max) * 100}%`,
                  minHeight: missing || value(m) === 0 ? 0 : "2px",
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="text-muted mt-1 flex justify-between font-mono text-[9px]">
        <span>{formatIdMonth(buckets[0].month, "short")}</span>
        <span>{formatIdMonth(last.month, "short")}</span>
      </div>
      <p className="sr-only">
        {label}: peak {format(value(peak))} in {formatIdMonth(peak.month)},{" "}
        {format(value(last))} in {formatIdMonth(last.month)}.
      </p>
    </div>
  );
}
