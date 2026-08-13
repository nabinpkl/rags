"use client";

import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";
import { cn } from "@/lib/utils";

/** The narrow-viewport top bar: the two things that stop being visible when
 * the columns collapse — the facet rail and the agent panel — get a way back.
 * Hidden from `lg:` up, where both are docked and neither needs a handle.
 *
 * The filters button hides in the viewer (`paper` set): filters belong to the
 * corpus list, and the viewer has its own "← corpus" affordance. It also hides
 * from `md:` up, where the rail is already docked beside the table.
 *
 * The agent button carries a live status dot because on a phone the panel is
 * a closed sheet — without it, a running turn would be invisible while the
 * user reads the paper it is citing. */
export function AppBar() {
  const paper = useViewerStore((state) => state.paper);
  const overlay = useUiShellStore((state) => state.overlay);
  const openFilters = useUiShellStore((state) => state.openFilters);
  const toggleAgent = useUiShellStore((state) => state.toggleAgent);
  const status = useAgentSessionStore((state) => state.status);

  const busy = status.kind === "streaming" || status.kind === "tool_running";

  return (
    <header className="bg-panel border-line flex items-center gap-2 border-b px-3 py-2 lg:hidden">
      {paper === null && (
        <button
          type="button"
          onClick={openFilters}
          aria-label="Open filters"
          aria-expanded={overlay === "filters"}
          className="border-line text-ink -ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded border md:hidden"
        >
          {/* Three bars, drawn not typed: a "☰" glyph renders at wildly
              different weights across platforms and is announced as text. */}
          <span aria-hidden="true" className="flex w-4 flex-col gap-[3px]">
            <span className="bg-ink h-[1.5px] w-full rounded" />
            <span className="bg-ink h-[1.5px] w-full rounded" />
            <span className="bg-ink h-[1.5px] w-full rounded" />
          </span>
        </button>
      )}

      <span className="text-ink font-serif text-[17px] font-semibold">askRAG</span>

      <button
        type="button"
        onClick={toggleAgent}
        aria-expanded={overlay === "agent"}
        className="border-line text-ink ml-auto flex h-9 items-center gap-2 rounded border px-3 text-[13px]"
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
    </header>
  );
}
