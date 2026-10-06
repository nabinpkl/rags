"use client";

import { useState } from "react";

import {
  QUERY_TYPES,
  RANKED_CONFIGS,
  type QueryRanks,
  method,
  ordinal,
  queryType,
  rankBand,
} from "@/lib/benchmarks/retrieval-benchmark";
import { cn } from "@/lib/utils";

const BAND_CLASS = {
  first: "bg-teal-ink text-panel font-semibold",
  near: "bg-teal-soft-strong text-teal-ink font-semibold",
  inside: "bg-teal-soft text-teal-ink",
  miss: "text-muted",
} as const;

/** Every query with each method's rank of its expected passage, as chips
 * shaded by band so the 93 rows scan as a heatmap. A two-passage query
 * carries one chip per passage. */
export function AllQueries({ queries, k }: { queries: QueryRanks[]; k: number }) {
  const [type, setType] = useState("");
  const rows = queries.filter((q) => !type || q.type === type);

  return (
    <div>
      <div className="text-muted mb-3 flex flex-wrap items-center gap-x-2.5 gap-y-2 text-[13px]">
        <label htmlFor="benchmark-query-type">Type</label>
        <select
          id="benchmark-query-type"
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="border-outline bg-panel text-ink min-h-9 rounded border px-2 py-1.5"
        >
          <option value="">All types</option>
          {Object.entries(QUERY_TYPES).map(([value, t]) => (
            <option key={value} value={value}>
              {t.name}
            </option>
          ))}
        </select>
        <span className="tabular-nums">{rows.length} queries</span>
        <span
          aria-hidden
          className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12px]"
        >
          <span className="inline-flex items-center gap-1.5">
            <Chip rank={1} k={k} />
            first
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Chip rank={3} k={k} />
            2nd–3rd
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Chip rank={7} k={k} />
            4th–{ordinal(k)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Chip rank={null} k={k} />
            missed
          </span>
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-[13.5px]">
          <thead>
            <tr className="border-outline text-muted border-b text-[12.5px]">
              <th scope="col" className="px-3 py-2 text-left font-semibold">
                Query
              </th>
              <th scope="col" className="px-3 py-2 text-left font-semibold">
                Type
              </th>
              {RANKED_CONFIGS.map((c) => (
                <th
                  key={c}
                  scope="col"
                  className="px-3 py-2 text-center font-semibold whitespace-nowrap"
                >
                  {COLUMN[c] ?? method(c).name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((q) => (
              <tr key={q.question} className="border-line border-t first:border-t-0">
                <td className="text-ink px-3 py-2 leading-snug">{q.question}</td>
                <td className="text-muted px-3 py-2 text-[12.5px] whitespace-nowrap">
                  {queryType(q.type).name}
                </td>
                {RANKED_CONFIGS.map((c) => (
                  <td key={c} className="w-[76px] px-3 py-2 text-center whitespace-nowrap">
                    <span className="inline-flex gap-1">
                      {(q.rank[c] ?? []).map((r, i) => (
                        <Chip key={i} rank={r} k={k} />
                      ))}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Short column heads: the full names are on the leaderboard above.
const COLUMN: Record<string, string> = {
  rerank: "Rerank",
  bm25: "Keyword",
  vector: "Semantic",
  rewrite: "Rewrite",
};

function Chip({ rank, k }: { rank: number | null; k: number }) {
  return (
    <span
      title={rank ? ordinal(rank) : `not in top ${k}`}
      className={cn(
        "inline-grid h-[22px] min-w-6 place-items-center rounded px-1.5 text-[12px] leading-none tabular-nums",
        BAND_CLASS[rankBand(rank)],
      )}
    >
      {rank ?? "–"}
    </span>
  );
}
