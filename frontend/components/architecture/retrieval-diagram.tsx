import { useId } from "react";

import { Arrow, ArrowDefs, Box, EdgeLabel, Figure } from "@/components/architecture/diagram-shapes";

/** Query to ranked chunks: two searches, fusion, then the reranker cuts the
 * pool to what the agent reads. `poolK` and `k` come from the benchmark
 * export, which records the depths the live search uses (config.py's
 * rerank_pool_k and search_top_k). */
export function RetrievalDiagram({
  poolK,
  k,
  chunkTokens,
}: {
  poolK: number;
  k: number;
  chunkTokens: number;
}) {
  const id = useId();
  return (
    <Figure
      viewBox="0 0 1000 390"
      label={`Retrieval: BM25 and vector search, ${poolK} chunks each; RRF fusion to ${poolK}; rerank-3-lite to the top ${k}.`}
    >
      <ArrowDefs id={id} />
      <Box x={15} y={145} w={135} h={90} title="Query" lines={["search_corpus"]} />

      <Box x={215} y={35} w={215} h={100} title="BM25" lines={["SQLite FTS5"]} />
      <Box x={215} y={245} w={215} h={100} title="Vector" lines={["pplx-embed, 512-d"]} />
      <Arrow id={id} d="M150 180 C172 180 166 85 187 85 H211" />
      <Arrow id={id} d="M150 200 C172 200 166 295 187 295 H211" />

      <Box x={490} y={140} w={160} h={100} title="Fusion" lines={["RRF"]} />
      <Arrow id={id} d="M430 85 C452 85 444 175 462 175 H486" />
      <Arrow id={id} d="M430 295 C452 295 444 205 462 205 H486" />
      <EdgeLabel x={442} y={72}>
        {poolK}
      </EdgeLabel>
      <EdgeLabel x={442} y={326}>
        {poolK}
      </EdgeLabel>

      <Box
        x={705}
        y={115}
        w={190}
        h={150}
        tone="teal"
        title="Reranker"
        lines={["rerank-3-lite", "cross-encoder"]}
      />
      <Arrow id={id} d="M650 190 H701" color="teal" />
      <EdgeLabel x={662} y={178}>
        {poolK}
      </EdgeLabel>

      <Box x={920} y={140} w={70} h={100} title={String(k)} lines={["top"]} />
      <Arrow id={id} d="M895 190 H916" color="teal" />

      <text x={20} y={380} className="fill-muted font-mono text-[15px] tracking-wide">
        {`${chunkTokens.toLocaleString("en")}-TOKEN CHUNKS · SECTION AND PAGE PER CHUNK`}
      </text>
    </Figure>
  );
}
