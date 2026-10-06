import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { type BoardRow, isBest, method, ms, pct, usd } from "@/lib/benchmarks/retrieval-benchmark";
import { cn } from "@/lib/utils";

/** Every method, best recall first. Recall carries its 95% interval as a bar
 * so a reader sees which gaps are ties; the other columns bold their best
 * value, compared as printed. */
export function Leaderboard({
  board,
  k,
  poolK,
  hardware,
}: {
  board: BoardRow[];
  k: number;
  poolK: number;
  hardware: string;
}) {
  const headers: { label: string; title: string }[] = [
    {
      label: `nDCG@${k}`,
      title: `Ranking quality of the top ${k}: 1.00 means the expected passage is always first`,
    },
    {
      label: "MRR",
      title: "Mean reciprocal rank: 1 / rank of the first expected passage, 1.00 is always first",
    },
    {
      label: `Paper@${k}`,
      title: `Share of queries with any passage of the expected paper in the top ${k}`,
    },
    {
      label: `Recall@${poolK}`,
      title: `Expected passages in the top ${poolK}: the most reordering that pool into the top ${k} can reach`,
    },
    {
      label: "Latency",
      title: `Median time per query on a ${hardware}; semantic includes the embedding call, rerank the reranker call, rewrite the model call`,
    },
    {
      label: "Cost",
      title:
        "Mean per query, as billed by the providers: the embedding, the rerank and the rewrite call",
    },
  ];

  return (
    <DashboardPanel title="Leaderboard" bodyClassName="px-0 pb-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px] border-collapse text-[13.5px]">
          <thead>
            <tr className="border-outline text-muted border-b text-[12.5px]">
              <th scope="col" className="w-8 py-2.5 pl-4 text-left font-semibold">
                #
              </th>
              <th scope="col" className="py-2.5 pl-2 text-left font-semibold">
                Method
              </th>
              <th scope="col" className="py-2.5 pl-4 text-left font-semibold">
                <Abbr
                  title={`Share of expected passages found in the top ${k}. The bar spans the 95% interval; overlapping bars are a tie`}
                >
                  Recall@{k}
                </Abbr>
              </th>
              {headers.map((h) => (
                <th
                  key={h.label}
                  scope="col"
                  className="py-2.5 pr-4 text-right font-semibold whitespace-nowrap"
                >
                  <Abbr title={h.title}>{h.label}</Abbr>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {board.map((row, i) => {
              const strong = (metric: Parameters<typeof isBest>[2], text: string) =>
                isBest(board, row, metric) ? <b className="font-bold">{text}</b> : text;
              const m = method(row.config);
              return (
                <tr
                  key={row.config}
                  className={cn("border-line border-t first:border-t-0", i === 0 && "bg-teal-soft")}
                >
                  <td className="text-muted py-3 pl-4 text-[13px] tabular-nums">{i + 1}</td>
                  <th scope="row" className="py-3 pl-2 text-left whitespace-nowrap">
                    <span className="text-ink block text-[14.5px] font-semibold">{m.name}</span>
                    <span className="text-muted block text-[12px] font-normal">{m.detail}</span>
                  </th>
                  <td className="py-3 pl-4">
                    <RecallCell row={row} />
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums">
                    {strong("ndcg", row.ndcg.toFixed(2))}
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums">
                    {strong("mrr", row.mrr.toFixed(2))}
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums">
                    {strong("paper", pct(row.paper))}
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums">
                    {strong("pool", pct(row.pool))}
                  </td>
                  <td className="py-3 pr-4 text-right whitespace-nowrap tabular-nums">
                    {strong("p50_ms", ms(row.p50_ms))}
                  </td>
                  <td className="py-3 pr-4 text-right whitespace-nowrap tabular-nums">
                    {strong("usd", usd(row.usd))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </DashboardPanel>
  );
}

function Abbr({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <abbr
      title={title}
      className="decoration-outline hover:decoration-current cursor-help underline decoration-dotted underline-offset-4"
    >
      {children}
    </abbr>
  );
}

function RecallCell({ row }: { row: BoardRow }) {
  const interval = row.lo !== null && row.hi !== null ? { lo: row.lo, hi: row.hi } : null;
  return (
    <div className="grid grid-cols-[64px_minmax(100px,1fr)] items-center gap-3">
      <span className="text-right">
        <span className="text-ink block text-[18px] font-bold tabular-nums">{pct(row.recall)}</span>
        {interval && (
          <span className="text-muted block text-[11.5px] tabular-nums">
            {pct(interval.lo)}–{pct(interval.hi)}
          </span>
        )}
      </span>
      <span
        role="img"
        aria-label={
          interval
            ? `95% interval ${pct(interval.lo)} to ${pct(interval.hi)}`
            : `no interval: run ${row.run_id} kept only totals`
        }
        title={interval ? undefined : `No interval: run ${row.run_id} kept only totals`}
        className="relative block h-4"
      >
        <span className="bg-line absolute inset-x-0 top-[7px] h-0.5" />
        {interval && (
          <span
            className="bg-teal-soft-strong border-teal-ink absolute top-[3px] h-2.5 rounded-xs border"
            style={{
              left: `${interval.lo * 100}%`,
              width: `${(interval.hi - interval.lo) * 100}%`,
            }}
          />
        )}
        <span
          className="bg-teal-ink absolute top-0 -ml-px h-4 w-[3px] rounded-[1px]"
          style={{ left: `${row.recall * 100}%` }}
        />
      </span>
    </div>
  );
}
