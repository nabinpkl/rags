"use client";

import { Sparkles } from "lucide-react";

import { useAgentPanel } from "@/hooks/use-agent-panel";
import { cn } from "@/lib/utils";
import { useAgentSessionStore } from "@/stores/agent-session-store";

/** Opens and closes the agent at every width: a docked column from `lg:` up,
 * a sheet below. The agent is on demand, so this is the only way in.
 *
 * It carries a live dot while a turn runs, because a closed panel hides
 * every other sign that one is running, including while the reader looks at
 * the paper the turn is citing. */
export function AgentButton() {
  const { open, toggle } = useAgentPanel();
  const status = useAgentSessionStore((state) => state.status);

  const busy = status.kind === "streaming" || status.kind === "tool_running";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-expanded={open}
      aria-controls="agent-panel"
      className={cn(
        "flex h-9 shrink-0 items-center gap-2 rounded border px-3 text-[13px] transition-colors motion-reduce:transition-none",
        // Both branches carry a hover, and the open one steps away from its
        // fill rather than toward the unselected look.
        open
          ? "border-teal-ink/30 bg-teal-soft text-teal-ink hover:bg-teal-soft-strong font-medium"
          : "border-line text-ink hover:bg-panel-hover",
      )}
    >
      <Sparkles className="size-4" aria-hidden />
      Agent
      {busy && (
        <span
          aria-hidden="true"
          className="bg-amber size-2 animate-pulse rounded-full motion-reduce:animate-none"
        />
      )}
    </button>
  );
}
