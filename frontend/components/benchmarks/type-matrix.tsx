import { DashboardPanel } from "@/components/landing/dashboard-panel";
import { type TypeRecall, method, pct, queryType } from "@/lib/benchmarks/retrieval-benchmark";
import { cn } from "@/lib/utils";

/** Recall per question type: where each method wins and where every method
 * struggles. Cell shade scales with recall; the best in each column (as
 * printed) is bold. */
export function TypeMatrix({
  byType,
  configs,
  k,
}: {
  byType: TypeRecall[];
  configs: string[];
  k: number;
}) {
  return (
    <DashboardPanel title={`Recall@${k} by query type`} bodyClassName="px-0 pb-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-[14px]">
          <thead>
            <tr className="border-outline text-muted border-b text-[12.5px]">
              <th scope="col" className="py-2.5 pl-4 text-left align-bottom font-semibold">
                Method
              </th>
              {byType.map((t) => (
                <th
                  key={t.type}
                  scope="col"
                  className="py-2.5 pr-4 text-right align-bottom leading-tight font-semibold"
                >
                  <abbr
                    title={queryType(t.type).detail}
                    className="decoration-outline hover:decoration-current cursor-help underline decoration-dotted underline-offset-4"
                  >
                    {queryType(t.type).name}
                  </abbr>
                  <span className="block text-[11px] font-normal tabular-nums">{t.n}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {configs.map((c) => (
              <tr key={c} className="border-line border-t first:border-t-0">
                <th
                  scope="row"
                  className="text-ink py-3 pl-4 text-left font-semibold whitespace-nowrap"
                >
                  {method(c).name}
                </th>
                {byType.map((t) => {
                  const v = t.recall[c] ?? 0;
                  const top = Math.max(...configs.map((x) => t.recall[x] ?? 0));
                  const best = Math.round(v * 100) === Math.round(top * 100);
                  return (
                    <td
                      key={t.type}
                      className={cn(
                        "text-ink py-3 pr-4 text-right tabular-nums",
                        best && "font-bold",
                      )}
                      style={{
                        background: `color-mix(in oklab, var(--color-teal) ${Math.round(v * 30)}%, var(--panel))`,
                      }}
                    >
                      {pct(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DashboardPanel>
  );
}
