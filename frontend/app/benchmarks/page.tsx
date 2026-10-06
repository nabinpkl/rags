import { AllQueries } from "@/components/benchmarks/all-queries";
import { Disclosure } from "@/components/benchmarks/disclosure";
import { ExampleQueries } from "@/components/benchmarks/example-queries";
import { Leaderboard } from "@/components/benchmarks/leaderboard";
import { MethodNotes } from "@/components/benchmarks/method-notes";
import { TypeMatrix } from "@/components/benchmarks/type-matrix";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { BENCHMARK } from "@/lib/benchmarks/retrieval-benchmark";

/** How well each retrieval method finds the passage that answers a question.
 * A STATIC route that reads no API (§4c decision 2 amendment 2026-10-06):
 * the data is the committed eval run, published by `just eval-publish`. */
export default function BenchmarksPage() {
  const data = BENCHMARK;
  const updated = new Date(`${data.exported}T00:00:00`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <DashboardShell
      current="benchmarks"
      trail={<li className="text-ink font-medium">Benchmarks</li>}
    >
      <div className="pt-2 pb-1">
        <h1 className="font-serif text-ink max-w-[24ch] text-[clamp(1.7rem,3.4vw,2.35rem)] leading-[1.1] font-bold text-balance">
          Retrieval benchmark
        </h1>
        <p className="text-ink-2 mt-3 max-w-[62ch] text-[15px] leading-snug">
          {data.n} questions over {data.n_papers.toLocaleString("en")} arXiv cs papers, scored at
          the top {data.k} passages the agent reads.
        </p>
        <p className="text-muted mt-1.5 text-[13px]">Updated {updated}</p>
      </div>

      <Leaderboard board={data.board} k={data.k} poolK={data.pool_k} hardware={data.hardware} />
      <TypeMatrix byType={data.by_type} configs={data.board.map((b) => b.config)} k={data.k} />

      <Disclosure title="Examples" meta={`${data.examples.length} queries`}>
        <ExampleQueries examples={data.examples} k={data.k} />
      </Disclosure>
      <Disclosure title="All queries" meta={`${data.n} queries`}>
        <AllQueries queries={data.queries} k={data.k} />
      </Disclosure>
      <Disclosure title="Method">
        <MethodNotes data={data} />
      </Disclosure>
    </DashboardShell>
  );
}
