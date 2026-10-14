import { useId } from "react";

import {
  Arrow,
  ArrowDefs,
  Box,
  EdgeLabel,
  Figure,
  Pill,
} from "@/components/architecture/diagram-shapes";

/** The agent's tools, in the registry's order (backend tools/registry.py). */
export const AGENT_TOOLS = ["search_corpus", "query_metadata", "read_paper", "drive_ui"] as const;

// Mirrors backend config.py: max_tool_steps_per_message, quote_max_words,
// max_quotes_per_paper. The frontend has no route to read them, so a change
// there is a change here.
export const MAX_ROUNDS = 8;
const QUOTE_WORDS = 50;
const QUOTES_PER_PAPER = 3;

/** One question through the loop: the budget gate, the model choosing
 * tools, fenced results coming back, and the answer with capped quotes. */
export function AgentDiagram() {
  const id = useId();
  return (
    <Figure
      viewBox="0 0 1000 400"
      label={`Agent: question, budget gate, Claude Haiku 4.5, four read-only tools, at most ${MAX_ROUNDS} rounds, fenced results, answer with quotes of at most ${QUOTE_WORDS} words, ${QUOTES_PER_PAPER} per paper.`}
    >
      <ArrowDefs id={id} />
      <Box x={20} y={105} w={155} h={90} title="Question" lines={["chat panel"]} />

      <Box
        x={215}
        y={95}
        w={175}
        h={110}
        tone="amber"
        title="Budget gate"
        lines={["tokens", "daily spend"]}
      />
      <Arrow id={id} d="M175 150 H211" />

      <Box
        x={430}
        y={85}
        w={195}
        h={130}
        tone="teal"
        title="Claude"
        lines={["Haiku 4.5", "tool choice"]}
      />
      <Arrow id={id} d="M390 150 H426" />

      <rect
        x={720}
        y={15}
        width={265}
        height={238}
        rx={12}
        strokeWidth={1.5}
        className="fill-panel-hover stroke-outline"
      />
      <text x={740} y={47} className="fill-muted font-mono text-[14px] tracking-wider">
        READ-ONLY TOOLS
      </text>
      {AGENT_TOOLS.map((tool, i) => (
        <Pill
          key={tool}
          x={740}
          y={62 + i * 46}
          w={225}
          label={tool}
          tone={tool === "search_corpus" ? "teal" : "plain"}
        />
      ))}

      <Arrow id={id} d="M625 118 C655 118 660 100 690 100 H716" color="teal" />
      <EdgeLabel x={630} y={82}>
        tool call
      </EdgeLabel>
      <Arrow id={id} d="M716 200 C686 200 681 182 655 182 H629" color="teal" />
      <EdgeLabel x={575} y={242}>
        fenced results
      </EdgeLabel>
      <rect
        x={835}
        y={266}
        width={150}
        height={36}
        rx={18}
        strokeWidth={2}
        className="fill-teal-soft stroke-teal-ink"
      />
      <text x={853} y={290} className="fill-teal-ink font-mono text-[16px] font-semibold">
        {`≤ ${MAX_ROUNDS} rounds`}
      </text>

      <Box
        x={430}
        y={300}
        w={360}
        h={90}
        title="Answer"
        lines={[`quotes ≤ ${QUOTE_WORDS} words, ≤ ${QUOTES_PER_PAPER} per paper`]}
      />
      <Arrow id={id} d="M527 215 V296" />
    </Figure>
  );
}
