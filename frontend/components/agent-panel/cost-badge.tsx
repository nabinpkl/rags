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
    // The dollar figure is the point (D11's public face, §7) and always shows;
    // the token split is detail that would push the panel header past 390px
    // once the counts reach six digits, so it waits for room.
    <span className="text-machine-muted font-mono text-[11px] whitespace-nowrap">
      <b className="text-amber font-semibold">${cost.cost_usd.toFixed(4)}</b>
      <span className="hidden sm:inline">
        {" "}
        · {cost.tokens_in.toLocaleString()} in / {cost.tokens_out.toLocaleString()} out
      </span>
    </span>
  );
}
