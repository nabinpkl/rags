import type { TrendsResponse } from "@/lib/api-client";

/** The corpus, month by month — papers arrived and references extracted.
//
// Two bar rows sharing one x-axis, because the series differ by an order of
// magnitude and a shared scale would flatten papers into noise. Only the
// trailing 24 months are legible as bars; the sentence below carries the
// whole-span totals so the chart cannot read as "the corpus is two years
// old". Same div-bar idiom as MethodsNote's cited-years chart. */
export function TrendsChart({ months }: { months: TrendsResponse["months"] }) {
  if (months.length === 0) return null;

  // The corpus is a rolling window with a thin held tail (~20 papers/month
  // of history against thousands in the window), so only the trailing twelve
  // months are legible as bars; the sentence below carries the whole-span
  // totals so the chart cannot read as "the corpus is one year old".
  const trailing = months.slice(-12);
  const maxPapers = Math.max(...trailing.map((m) => m.papers_added), 1);
  const maxRefs = Math.max(...trailing.map((m) => m.refs_made), 1);
  const totalPapers = months.reduce((sum, m) => sum + m.papers_added, 0);
  const totalRefs = months.reduce((sum, m) => sum + m.refs_made, 0);
  const last = trailing[trailing.length - 1];

  return (
    <div id="trends" className="bg-panel border-line scroll-mt-20 rounded border p-5">
      <h2 className="font-serif text-ink mb-1 text-xl font-semibold">
        The corpus, month by month
      </h2>
        <p className="text-muted mb-4 max-w-[70ch] text-sm">
          {totalPapers.toLocaleString()} papers, {totalRefs.toLocaleString()} references
          extracted, {formatMonth(months[0].month)} to {formatMonth(last.month)}. Showing the
          trailing twelve months — {last.papers_added.toLocaleString()} papers and{" "}
          {last.refs_made.toLocaleString()} references in {formatMonth(last.month)} alone.
        </p>
        <div className="grid gap-5">
          <BarRow
            label="papers arrived"
            buckets={trailing}
            value={(m) => m.papers_added}
            max={maxPapers}
            barClass="bg-teal"
          />
          <BarRow
            label="references extracted"
            buckets={trailing}
            value={(m) => m.refs_made}
            max={maxRefs}
            barClass="bg-muted"
          />
        </div>
    </div>
  );
}

function BarRow({
  label,
  buckets,
  value,
  max,
  barClass,
}: {
  label: string;
  buckets: TrendsResponse["months"];
  value: (m: TrendsResponse["months"][number]) => number;
  max: number;
  barClass: string;
}) {
  return (
    <div>
      <p className="text-muted mb-2 font-mono text-[10.5px] tracking-[0.1em] uppercase">{label}</p>
      <div className="flex items-end gap-1" aria-hidden>
        {buckets.map((m, i) => (
          <div key={m.month} className="flex flex-1 flex-col items-center gap-1">
            <div
              className={`${barClass} w-full rounded-t-sm`}
              style={{ height: `${Math.max((value(m) / max) * 120, 3)}px` }}
              title={`${m.month}: ${value(m).toLocaleString()} ${label}`}
            />
            {i % 4 === 0 && (
              <span className="text-muted font-mono text-[9px]">{shortMonth(m.month)}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** "2026-09" to "September 2026"; "Sep ’26" for the axis. String splits,
 * never date parsing — the API's month is already canonical. */
function formatMonth(month: string): string {
  const [year, mon] = month.split("-");
  if (!year || !mon) return month;
  const name = new Date(Date.UTC(Number(year), Number(mon) - 1, 1)).toLocaleString("en-US", {
    month: "long",
    timeZone: "UTC",
  });
  return `${name} ${year}`;
}

function shortMonth(month: string): string {
  const [year, mon] = month.split("-");
  if (!year || !mon) return month;
  const name = new Date(Date.UTC(Number(year), Number(mon) - 1, 1)).toLocaleString("en-US", {
    month: "short",
    timeZone: "UTC",
  });
  return `${name} ’${year.slice(2)}`;
}
