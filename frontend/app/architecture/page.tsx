import { AgentDiagram } from "@/components/architecture/agent-diagram";
import { ArchitectureSection } from "@/components/architecture/architecture-section";
import { RecallBars } from "@/components/architecture/recall-bars";
import { RetrievalDiagram } from "@/components/architecture/retrieval-diagram";
import { TurnSequence } from "@/components/architecture/turn-sequence";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { BENCHMARK } from "@/lib/benchmarks/retrieval-benchmark";

/** How retrieval with reranking and the agent are built, and where they
 * meet. A STATIC route like /benchmarks: the depths and recall figures come
 * from the committed eval export, the rest is drawn. */
export default function ArchitecturePage() {
  const data = BENCHMARK;
  return (
    <DashboardShell
      current="architecture"
      trail={<li className="text-ink font-medium">Architecture</li>}
    >
      <div className="flex flex-col gap-12 pb-8">
        <div className="pt-2">
          <h1 className="font-serif text-ink text-[clamp(1.9rem,3.8vw,2.6rem)] leading-[1.1] font-bold text-balance">
            Architecture
          </h1>
          <p className="text-ink-2 mt-3 max-w-[62ch] text-[18px] leading-snug">
            Hybrid retrieval, reranking, and the agent loop.
          </p>
        </div>

        <ArchitectureSection
          id="retrieval"
          title="Retrieval"
          subtitle={`BM25 and vector search, rank fusion, a reranked top ${data.k}.`}
        >
          <RetrievalDiagram poolK={data.pool_k} k={data.k} chunkTokens={data.chunk_size_tokens} />
          <RecallBars board={data.board} k={data.k} n={data.n} />
        </ArchitectureSection>

        <ArchitectureSection
          id="agent"
          title="Agent"
          subtitle="Claude Haiku 4.5, four read-only tools, a budget gate."
        >
          <AgentDiagram />
        </ArchitectureSection>

        <ArchitectureSection
          id="one-turn"
          title="One turn"
          subtitle="Question to cited answer, with retrieval behind each tool call."
        >
          <TurnSequence k={data.k} />
        </ArchitectureSection>
      </div>
    </DashboardShell>
  );
}
