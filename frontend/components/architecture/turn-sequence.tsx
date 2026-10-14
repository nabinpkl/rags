import { useId } from "react";

import { MAX_ROUNDS } from "@/components/architecture/agent-diagram";
import { Arrow, ArrowDefs, EdgeLabel, Figure } from "@/components/architecture/diagram-shapes";

const LANES = [
  { name: "Reader", x: 120, tone: "plain" },
  { name: "Claude", x: 360, tone: "teal" },
  { name: "Tools", x: 610, tone: "soft" },
  { name: "Retrieval", x: 870, tone: "teal" },
] as const;

const HEAD: Record<(typeof LANES)[number]["tone"], string> = {
  plain: "fill-panel stroke-outline",
  soft: "fill-panel-hover stroke-outline",
  teal: "fill-teal-soft stroke-teal-ink",
};

/** One turn as a sequence: where the agent meets retrieval. Every search is
 * a tool call, and what comes back is fenced before the model reads it. */
export function TurnSequence({ k }: { k: number }) {
  const id = useId();
  const [reader, claude, tools, retrieval] = LANES.map((lane) => lane.x);
  return (
    <Figure
      viewBox="0 0 1000 600"
      label={`One turn: the reader asks; Claude calls search_corpus, which fuses and reranks to ${k} chunks returned fenced; Claude calls read_paper for page text; drive_ui opens the cited page for the reader; Claude answers with quotes.`}
    >
      <ArrowDefs id={id} />
      {LANES.map((lane) => (
        <g key={lane.name}>
          <rect
            x={lane.x - 90}
            y={18}
            width={180}
            height={56}
            rx={10}
            strokeWidth={lane.tone === "teal" ? 2 : 1.5}
            className={HEAD[lane.tone]}
          />
          <text
            x={lane.x}
            y={53}
            textAnchor="middle"
            className="fill-ink font-sans text-[20px] font-bold"
          >
            {lane.name}
          </text>
          <path
            d={`M${lane.x} 74 V585`}
            fill="none"
            strokeWidth={1.5}
            strokeDasharray="5 6"
            className="stroke-outline"
          />
        </g>
      ))}

      <rect
        x={300}
        y={158}
        width={620}
        height={304}
        rx={12}
        fill="none"
        strokeWidth={1.5}
        strokeDasharray="6 6"
        className="stroke-outline"
      />
      <text x={376} y={184} className="fill-muted font-mono text-[14px] tracking-wider">
        {`UP TO ${MAX_ROUNDS} ROUNDS`}
      </text>

      <Arrow id={id} d={`M${reader} 130 H${claude - 4}`} />
      <EdgeLabel x={reader + 20} y={118} mono={false}>
        question
      </EdgeLabel>

      <Arrow id={id} d={`M${claude} 222 H${tools - 4}`} color="teal" />
      <EdgeLabel x={claude + 20} y={210}>
        search_corpus
      </EdgeLabel>
      <Arrow id={id} d={`M${tools} 252 H${retrieval - 4}`} color="teal" />
      <EdgeLabel x={tools + 20} y={240} mono={false}>
        fuse + rerank
      </EdgeLabel>
      <Arrow id={id} d={`M${retrieval} 292 H${tools + 4}`} color="teal" dashed />
      <EdgeLabel x={tools + 50} y={280} mono={false}>{`${k} chunks`}</EdgeLabel>
      <Arrow id={id} d={`M${tools} 322 H${claude + 4}`} color="teal" dashed />
      <EdgeLabel x={claude + 40} y={310} mono={false}>
        fenced chunks
      </EdgeLabel>

      <Arrow id={id} d={`M${claude} 377 H${tools - 4}`} />
      <EdgeLabel x={claude + 20} y={365}>
        read_paper
      </EdgeLabel>
      <Arrow id={id} d={`M${tools} 407 H${retrieval - 4}`} />
      <EdgeLabel x={tools + 20} y={395} mono={false}>
        page text
      </EdgeLabel>
      <Arrow id={id} d={`M${retrieval} 442 H${claude + 4}`} dashed />
      <EdgeLabel x={tools - 50} y={430} mono={false}>
        fenced text
      </EdgeLabel>

      <Arrow id={id} d={`M${claude} 502 H${reader + 4}`} />
      <EdgeLabel x={reader + 26} y={490}>
        drive_ui: open page
      </EdgeLabel>
      <Arrow id={id} d={`M${claude} 557 H${reader + 4}`} color="teal" />
      <EdgeLabel x={reader + 26} y={545} mono={false}>
        answer + quotes
      </EdgeLabel>
    </Figure>
  );
}
