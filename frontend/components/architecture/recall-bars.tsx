import { type BoardRow, method, ms, pct } from "@/lib/benchmarks/retrieval-benchmark";
import { cn } from "@/lib/utils";

/** What each retrieval step adds, from the benchmark run: the two searches,
 * their fusion, then fusion plus rerank, which is what live search runs. */
const STEPS = ["bm25", "vector", "hybrid", "rerank"] as const;

export function RecallBars({ board, k, n }: { board: BoardRow[]; k: number; n: number }) {
  const rows = STEPS.map((config) => {
    const row = board.find((b) => b.config === config);
    if (!row) throw new Error(`benchmark export has no ${config} row`);
    return row;
  });

  return (
    <div className="bg-panel border-outline flex flex-col gap-3 rounded-lg border p-5">
      <p className="text-muted font-mono text-[13px] tracking-wide uppercase">
        Recall@{k} · {n} questions · median latency
      </p>
      <ul className="flex flex-col gap-3">
        {rows.map((row) => {
          const live = row.config === "rerank";
          return (
            <li
              key={row.config}
              className="grid grid-cols-[1fr_auto_auto] items-center gap-x-4 gap-y-1.5 sm:grid-cols-[11rem_1fr_auto_auto]"
            >
              <span className="text-ink flex items-center gap-2 text-[17px]">
                {method(row.config).name}
                {live && (
                  <span className="bg-teal-soft text-teal-ink rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold tracking-wide uppercase">
                    live
                  </span>
                )}
              </span>
              <span className="border-line bg-panel-hover col-span-3 row-start-2 h-7 overflow-hidden rounded border sm:col-span-1 sm:row-start-auto">
                <span
                  className={cn("block h-full", live ? "bg-chart-2" : "bg-chart-1")}
                  style={{ width: pct(row.recall) }}
                />
              </span>
              <span className="text-ink text-right font-mono text-[17px] font-semibold tabular-nums">
                {pct(row.recall)}
              </span>
              <span className="text-muted w-20 text-right font-mono text-[15px] tabular-nums">
                {ms(row.p50_ms)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
