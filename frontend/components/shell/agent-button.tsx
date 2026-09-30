"use client";

import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { cn } from "@/lib/utils";

/** The way back to the agent below `lg:`, where its panel is a closed sheet
 * rather than a docked column. Hidden from `lg:` up, where it has nothing to
 * open.
 *
 * It carries a live status dot because a closed sheet hides every other sign
 * that a turn is running, including while the reader looks at the paper the
 * turn is citing. */
export function AgentButton() {
  const overlay = useUiShellStore((state) => state.overlay);
  const toggleAgent = useUiShellStore((state) => state.toggleAgent);
  const status = useAgentSessionStore((state) => state.status);

  const busy = status.kind === "streaming" || status.kind === "tool_running";

  return (
    <button
      type="button"
      onClick={toggleAgent}
      aria-expanded={overlay === "agent"}
      className="border-line text-ink hover:bg-panel-hover flex h-9 shrink-0 items-center gap-2 rounded border px-3 text-[13px] transition-colors motion-reduce:transition-none lg:hidden"
    >
      <span
        aria-hidden="true"
        className={cn(
          "h-2 w-2 rounded-full",
          busy ? "bg-amber animate-pulse motion-reduce:animate-none" : "bg-teal",
        )}
      />
      Agent
    </button>
  );
}
