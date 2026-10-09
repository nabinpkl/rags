import raw from "@/lib/benchmarks/retrieval.json";

/** The retrieval benchmark, as `just eval-publish` wrote it from the
 * committed eval run (DECISIONS.md 2026-10-06). Imported at build time: the
 * numbers change only when a run is committed, so the page reads no API.
 *
 * The JSON is assigned to these types below, so a field the exporter renames
 * or drops fails `tsc` rather than the page.
 */
export type BoardRow = {
  config: string;
  recall: number;
  /** 95% bootstrap interval; null for a pinned row that kept only totals. */
  lo: number | null;
  hi: number | null;
  ndcg: number;
  mrr: number;
  paper: number;
  pool: number;
  p50_ms: number;
  usd: number;
  /** Set only on a pinned row: the run its totals came from. */
  run_id: string | null;
};

export type TypeRecall = { type: string; n: number; recall: Record<string, number> };

/** Rank of each expected passage (two for a two-passage query); null is a miss. */
export type QueryRanks = {
  question: string;
  type: string;
  rank: Record<string, (number | null)[]>;
};

export type Passage = { id: string; paper: string; section: string; title: string };

/** 2 is the expected passage, 1 another passage of its paper, 0 another paper. */
export type GradedPassage = Passage & { grade: number };

export type Example = {
  question: string;
  type: string;
  expected: Passage;
  rank: Record<string, number | null>;
  hybrid: GradedPassage[];
  rerank: GradedPassage[];
};

export type RetrievalBenchmark = {
  run_id: string;
  exported: string;
  drafted: number;
  n_papers: number;
  n_chunks: number;
  draft_models: string[];
  check_models: string[];
  rewrite_models: string[];
  embedding_model: string;
  embedding_dims: number;
  chunk_size_tokens: number;
  chunk_overlap_ratio: number;
  rrf_k: number;
  rerank_model: string;
  local_rerank_model: string;
  local_rerank_run_id: string;
  bootstrap_resamples: number;
  hardware: string;
  k: number;
  pool_k: number;
  n: number;
  board: BoardRow[];
  by_type: TypeRecall[];
  queries: QueryRanks[];
  examples: Example[];
};

export const BENCHMARK: RetrievalBenchmark = raw;

/** Row names and the one-line "what it is" under each. */
export const METHODS: Record<string, { name: string; detail: string }> = {
  rerank: { name: "Hybrid + rerank", detail: "Voyage rerank-3-lite, top 50" },
  rerank_local: { name: "Hybrid + local rerank", detail: "gte-modernbert, 4-core Arm CPU" },
  hybrid: { name: "Hybrid", detail: "keyword + semantic, RRF" },
  bm25: { name: "Keyword", detail: "BM25" },
  vector: { name: "Semantic", detail: "pplx-embed, 512 dims" },
  rewrite: { name: "Rewrite + hybrid", detail: "one model rewrite of the query" },
};

/** Question types in the reader's words, with what each one tests. */
export const QUERY_TYPES: Record<string, { name: string; detail: string }> = {
  single_hop: { name: "Plain lookup", detail: "Asks what one passage says" },
  exact_match: { name: "Named term", detail: "Names an acronym, model or benchmark" },
  vocabulary_mismatch: {
    name: "Unfamiliar wording",
    detail:
      "Shares no word with its passage that appears in fewer than 500 passages, as someone who has not read the paper",
  },
  known_hard: { name: "Table or math", detail: "Answered by a table or an equation" },
  multi_hop: {
    name: "Two passages",
    detail: "Needs two passages of one paper; finding one scores half",
  },
};

/** The per-query columns, in the board's order of strength. */
export const RANKED_CONFIGS = ["rerank", "hybrid", "bm25", "vector", "rewrite"] as const;

export function method(config: string): { name: string; detail: string } {
  const m = METHODS[config];
  if (!m) throw new Error(`no label for retrieval config "${config}"`);
  return m;
}

export function queryType(type: string): { name: string; detail: string } {
  const t = QUERY_TYPES[type];
  if (!t) throw new Error(`no label for query type "${type}"`);
  return t;
}

export const pct = (v: number) => `${Math.round(v * 100)}%`;

/** Dollars in plain decimals; anything under a millionth (a query embedding
 * is about $0.00000004) reads as that bound. */
export function usd(v: number): string {
  if (v === 0) return "$0";
  if (v < 1e-6) return "<$0.000001";
  return `$${v.toFixed(6).replace(/0+$/, "")}`;
}

export function ms(v: number): string {
  if (v < 1000) return `${Math.round(v)} ms`;
  return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)} s`;
}

export function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return n + ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th");
}

type Metric = "ndcg" | "mrr" | "paper" | "pool" | "p50_ms" | "usd";

/** Whether a row holds the column's best value, compared as printed: two
 * shares that both print 93% are both best. Dollars compare exactly, since
 * their printed form keeps every significant digit. */
export function isBest(rows: BoardRow[], row: BoardRow, metric: Metric): boolean {
  const lower = metric === "p50_ms" || metric === "usd";
  const shown = (v: number) => (metric === "usd" ? v : Math.round(v * 100));
  const values = rows.map((r) => shown(r[metric]));
  return shown(row[metric]) === (lower ? Math.min(...values) : Math.max(...values));
}

/** Colour band of a rank chip: first, near the top, inside the top k, missed. */
export function rankBand(rank: number | null): "first" | "near" | "inside" | "miss" {
  if (rank === null) return "miss";
  if (rank === 1) return "first";
  return rank <= 3 ? "near" : "inside";
}

/** What the reranker did to hybrid's rank of the expected passage. */
export function rerankMove(rank: Record<string, number | null>): "up" | "same" | "down" | "missed" {
  const before = rank.hybrid ?? null;
  const after = rank.rerank ?? null;
  if (before === null && after === null) return "missed";
  if (after !== null && (before === null || after < before)) return "up";
  return after === before ? "same" : "down";
}
