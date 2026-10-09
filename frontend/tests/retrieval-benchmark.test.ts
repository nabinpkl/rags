import { describe, expect, it } from "vitest";

import {
  BENCHMARK,
  type BoardRow,
  isBest,
  method,
  ms,
  ordinal,
  queryType,
  rankBand,
  rerankMove,
  usd,
} from "@/lib/benchmarks/retrieval-benchmark";

function row(over: Partial<BoardRow>): BoardRow {
  return {
    config: "hybrid",
    recall: 0.8,
    lo: 0.7,
    hi: 0.9,
    ndcg: 0.5,
    mrr: 0.5,
    paper: 0.9,
    pool: 0.9,
    p50_ms: 200,
    usd: 0,
    run_id: null,
    ...over,
  };
}

describe("formatters", () => {
  it("prints dollars in plain decimals and floors the tiny ones", () => {
    expect(usd(0)).toBe("$0");
    expect(usd(4e-8)).toBe("<$0.000001");
    expect(usd(0.0006594)).toBe("$0.000659");
  });

  it("prints latency in ms below a second and seconds above", () => {
    expect(ms(97.02)).toBe("97 ms");
    expect(ms(5039)).toBe("5.0 s");
    expect(ms(153433)).toBe("153 s");
  });

  it("gives teens their th", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual([
      "1st",
      "2nd",
      "3rd",
      "4th",
      "11th",
      "12th",
      "13th",
      "21st",
      "22nd",
    ]);
  });
});

describe("isBest", () => {
  it("treats two shares that print the same as both best", () => {
    const rows = [row({ pool: 0.9301 }), row({ pool: 0.9302 }), row({ pool: 0.89 })];
    expect(rows.map((r) => isBest(rows, r, "pool"))).toEqual([true, true, false]);
  });

  it("wants the lowest latency and cost, and compares dollars exactly", () => {
    const rows = [row({ usd: 4.1e-8, p50_ms: 97 }), row({ usd: 4.2e-8, p50_ms: 215 })];
    expect(isBest(rows, rows[0], "usd")).toBe(true);
    expect(isBest(rows, rows[1], "usd")).toBe(false);
    expect(isBest(rows, rows[0], "p50_ms")).toBe(true);
  });
});

describe("rankBand and rerankMove", () => {
  it("bands a rank by how soon the reader meets it", () => {
    expect([1, 2, 3, 4, 10, null].map(rankBand)).toEqual([
      "first",
      "near",
      "near",
      "inside",
      "inside",
      "miss",
    ]);
  });

  it("reads the reranker's effect on hybrid's rank", () => {
    expect(rerankMove({ hybrid: 8, rerank: 1 })).toBe("up");
    expect(rerankMove({ hybrid: null, rerank: 1 })).toBe("up");
    expect(rerankMove({ hybrid: 4, rerank: 4 })).toBe("same");
    expect(rerankMove({ hybrid: 5, rerank: null })).toBe("down");
    expect(rerankMove({ hybrid: null, rerank: null })).toBe("missed");
  });
});

describe("the committed export", () => {
  it("names every config and query type it carries", () => {
    for (const b of BENCHMARK.board) expect(() => method(b.config)).not.toThrow();
    for (const t of BENCHMARK.by_type) expect(() => queryType(t.type)).not.toThrow();
  });

  it("fails loud on a config it has no label for", () => {
    expect(() => method("splade")).toThrow(/splade/);
  });

  it("ranks the board best first and pins only the run-less row", () => {
    const recalls = BENCHMARK.board.map((b) => b.recall);
    expect(recalls).toEqual([...recalls].sort((a, b) => b - a));
    for (const b of BENCHMARK.board) expect(b.lo === null).toBe(b.run_id !== null);
  });
});
