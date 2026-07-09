import type { CostEvent } from "@/lib/sse";

interface CostBadgeProps {
  cost: CostEvent | null;
}

/** One turn's cost, from the terminal `cost` event — the loop has no
 * intra-turn per-step cost to stream (sse_events.py's `cost_event()`
 * docstring), so there is nothing to show until the turn is done. */
export function CostBadge({ cost }: CostBadgeProps) {
  if (cost === null) return null;
  return (
    <span className="text-machine-muted font-mono text-[11px]">
      <b className="text-amber font-semibold">${cost.cost_usd.toFixed(4)}</b> ·{" "}
      {cost.tokens_in.toLocaleString()} in / {cost.tokens_out.toLocaleString()} out
    </span>
  );
}
