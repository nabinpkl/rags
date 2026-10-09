import type { ReactNode } from "react";

import type { RetrievalBenchmark } from "@/lib/benchmarks/retrieval-benchmark";

/** How the run was made, each fact read from the export rather than typed
 * here, so a new run cannot leave a stale model name behind. */
export function MethodNotes({ data }: { data: RetrievalBenchmark }) {
  const id = (s: string) => <span className="font-mono text-[12px]">{s}</span>;
  const list = (xs: string[]) =>
    xs.map((x, i) => (
      <span key={x}>
        {i > 0 && ", "}
        {id(x)}
      </span>
    ));

  const rows: [string, ReactNode][] = [
    [
      "Queries",
      <>
        {data.n} counted of {data.drafted} drafted, at most 12 words, {id("evals/golden.jsonl")}
      </>,
    ],
    [
      "Checked by",
      <>
        drafted by {list(data.draft_models)}, checked by {list(data.check_models)}, ambiguous
        answers culled
      </>,
    ],
    ["Relevance", "one expected passage per query (two for two-passage queries)"],
    [
      "Corpus",
      `${data.n_papers.toLocaleString("en")} arXiv cs papers, ${data.n_chunks.toLocaleString("en")} passages`,
    ],
    [
      "Chunking",
      <>
        section-aware, up to {data.chunk_size_tokens.toLocaleString("en")} tokens (
        {id("cl100k_base")}), {Math.round(data.chunk_overlap_ratio * 100)}% overlap
      </>,
    ],
    ["Keyword", "SQLite FTS5 BM25, porter stemming, terms OR-joined"],
    [
      "Semantic",
      <>
        {id(data.embedding_model)}, {data.embedding_dims} dims, cosine, Chroma HNSW
      </>,
    ],
    [
      "Hybrid",
      <>
        reciprocal rank fusion, {id(`k = ${data.rrf_k}`)}, over each search&apos;s top {data.k}
      </>,
    ],
    [
      "Rerank",
      <>
        {id(data.rerank_model)} through OpenRouter over hybrid&apos;s top {data.pool_k}; local:{" "}
        {id(data.local_rerank_model)} on a {data.hardware}, run {id(data.local_rerank_run_id)}
      </>,
    ],
    [
      "Rewrite",
      <>
        one rewrite per query by {list(data.rewrite_models)}, the agent&apos;s model, then hybrid
      </>,
    ],
    [
      "Interval",
      `95% bootstrap over queries, ${data.bootstrap_resamples.toLocaleString("en")} resamples`,
    ],
    ["Latency", `median per query on a ${data.hardware}`],
    ["Cost", "mean per query, from each provider's billed figure"],
    ["Run", id(data.run_id)],
  ];

  return (
    <div className="@container">
      <dl className="grid gap-x-8 @3xl:grid-cols-2">
        {rows.map(([term, detail]) => (
          <div
            key={term}
            className="border-line grid gap-0.5 border-b py-2.5 text-[13.5px] @md:grid-cols-[132px_minmax(0,1fr)] @md:gap-3"
          >
            <dt className="text-muted">{term}</dt>
            <dd className="text-ink [overflow-wrap:anywhere]">{detail}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
