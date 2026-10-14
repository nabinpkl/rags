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
      label={`A query runs keyword and meaning search, ${poolK} chunks each; rank fusion keeps ${poolK}; a reranker reading the query and each chunk together returns the top ${k}.`}
    >
      <ArrowDefs id={id} />
      <Box x={20} y={145} w={140} h={90} title="Query" lines={["from a tool"]} />

      <Box x={215} y={35} w={215} h={100} title="Keyword" lines={["BM25 over chunks"]} />
      <Box x={215} y={245} w={215} h={100} title="Meaning" lines={["512-d embeddings"]} />
      <Arrow id={id} d="M160 180 C190 180 190 85 211 85" />
      <Arrow id={id} d="M160 200 C190 200 190 295 211 295" />

      <Box x={490} y={140} w={160} h={100} title="Fuse" lines={["rank fusion"]} />
      <Arrow id={id} d="M430 85 C465 85 460 175 486 175" />
      <Arrow id={id} d="M430 295 C465 295 460 205 486 205" />
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
        title="Rerank"
        lines={["reads the query", "and each chunk", "together"]}
      />
      <Arrow id={id} d="M650 190 H701" color="teal" />
      <EdgeLabel x={662} y={178}>
        {poolK}
      </EdgeLabel>

      <Box x={920} y={140} w={70} h={100} title={String(k)} lines={["best"]} />
      <Arrow id={id} d="M895 190 H916" color="teal" />

      <text x={20} y={380} className="fill-muted font-mono text-[15px] tracking-wide">
        {`${chunkTokens.toLocaleString("en")}-TOKEN CHUNKS · EACH KEEPS ITS SECTION AND PAGE`}
      </text>
    </Figure>
  );
}
