import { ChartColumn } from "lucide-react";

import type { TrendsResponse } from "@/lib/api-client";

const CHART_MONTHS = 12;
/** Below this the bars stop reading as a series; above it the rows grow to
 * fill whatever height the dashboard row gives the card, so the card never
 * ends in a band of empty panel. */
const MIN_ROW_HEIGHT_PX = 64;

/** Corpus growth, month by month.
 *
 * Two rows rather than one grouped chart: references outrun papers by an
 * order of magnitude, so a shared scale would flatten the papers row onto the
 * baseline. Each row therefore prints its OWN peak in the corner — two scales
 * in one card is only honest if both are stated, and a bar chart whose scale
 * is implied is decoration.
 *
 * Most of the trailing year sits near zero on purpose, and the second row is
 * flat-zero for the same months: those are the older works the ingest window
 * cites, held so they can be read but never parsed for references of their
 * own. Without the subtitle saying so, empty months read as a broken chart.
 */
export function TrendsChart({ months }: { months: TrendsResponse["months"] }) {
  if (months.length === 0) return null;

  const trailing = months.slice(-CHART_MONTHS);
  const totalPapers = months.reduce((sum, m) => sum + m.papers_added, 0);
  const totalRefs = months.reduce((sum, m) => sum + m.refs_made, 0);
  const last = trailing[trailing.length - 1];

  return (
    <section
      id="trends"
      className="bg-panel border-line scroll-mt-20 flex h-full flex-col rounded border p-5"
    >
      <div className="mb-1 flex items-center gap-2">
        <ChartColumn className="text-chart-1 size-[18px] shrink-0" aria-hidden />
        <h2 className="font-serif text-ink text-xl font-semibold">The corpus, month by month</h2>
        <span className="text-muted ml-auto shrink-0 font-mono text-[10.5px] tracking-[0.08em] uppercase">
          {shortMonth(trailing[0].month)} – {shortMonth(last.month)}
        </span>
      </div>
      <p className="text-muted mb-5 max-w-[62ch] text-[13px] leading-relaxed">
        {totalPapers.toLocaleString()} papers, {totalRefs.toLocaleString()} references extracted,{" "}
        {formatMonth(months[0].month)} to {formatMonth(last.month)}. The recent spike is the
        ingest window; the quiet months before it are the older work that window cites, held to
        be read but never parsed for references of their own.
      </p>
      <div className="flex min-h-0 flex-1 flex-col gap-6">
        <BarRow
          label="papers arrived"
          buckets={trailing}
          value={(m) => m.papers_added}
          colorClass="bg-chart-1"
        />
        <BarRow
          label="references extracted"
          buckets={trailing}
          value={(m) => m.refs_made}
          colorClass="bg-chart-2"
        />
      </div>
    </section>
  );
}

function BarRow({
  label,
  buckets,
  value,
  colorClass,
}: {
  label: string;
  buckets: TrendsResponse["months"];
  value: (m: TrendsResponse["months"][number]) => number;
  colorClass: string;
}) {
  const max = Math.max(...buckets.map(value), 1);
  const peak = buckets.reduce((best, m) => (value(m) > value(best) ? m : best), buckets[0]);
  const last = buckets[buckets.length - 1];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p className="text-ink flex items-center gap-1.5 font-mono text-[10.5px] tracking-[0.1em] uppercase">
          <span className={`${colorClass} size-2 shrink-0 rounded-[1px]`} aria-hidden />
          {label}
        </p>
        <p className="text-muted shrink-0 font-mono text-[10.5px] tabular-nums">
          peak {value(peak).toLocaleString()}
        </p>
      </div>
      <div
        className="border-line flex min-h-0 flex-1 items-end gap-[3px] border-b"
        style={{ minHeight: `${MIN_ROW_HEIGHT_PX}px` }}
        aria-hidden
      >
        {buckets.map((m) => (
          <div
            key={m.month}
            className="hover:bg-teal-soft relative h-full flex-1 rounded-t-sm transition-colors motion-reduce:transition-none"
            title={`${m.month}: ${value(m).toLocaleString()} ${label}`}
          >
            {/* Bars are a PERCENTAGE of the track, not a pixel height, so the
                card fills whatever the dashboard row hands it. A zero month
                draws nothing: a minimum stub would render a quantity that is
                not there. */}
            <div
              className={`${colorClass} absolute inset-x-0 bottom-0 rounded-t-sm`}
              style={{
                height: value(m) === 0 ? 0 : `${(value(m) / max) * 100}%`,
                minHeight: value(m) === 0 ? 0 : "2px",
              }}
            />
          </div>
        ))}
      </div>
      <div className="text-muted mt-1 flex justify-between font-mono text-[9px]">
        <span>{shortMonth(buckets[0].month)}</span>
        <span>{shortMonth(last.month)}</span>
      </div>
      <p className="sr-only">
        {label}: peak {value(peak).toLocaleString()} in {formatMonth(peak.month)},{" "}
        {value(last).toLocaleString()} in {formatMonth(last.month)}.
      </p>
    </div>
  );
}

/** "2026-09" to "September 2026"; "Sep ’26" for the axis. String splits,
 * never date parsing — the API's month is already canonical. */
function formatMonth(month: string): string {
  const [year, mon] = month.split("-");
  if (!year || !mon) return month;
  return `${monthName(year, mon, "long")} ${year}`;
}

function shortMonth(month: string): string {
  const [year, mon] = month.split("-");
  if (!year || !mon) return month;
  return `${monthName(year, mon, "short")} ’${year.slice(2)}`;
}

function monthName(year: string, mon: string, month: "long" | "short"): string {
  return new Date(Date.UTC(Number(year), Number(mon) - 1, 1)).toLocaleString("en-US", {
    month,
    timeZone: "UTC",
  });
}
