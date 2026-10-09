"use client";

import { useMediaQuery } from "@/hooks/use-media-query";
import { MEDIA_AGENT_DOCKED } from "@/lib/breakpoints";
import { useUiShellStore } from "@/stores/ui-shell-store";

/** The agent panel's open state, as the control in front of the reader
 * means it: a docked column from `lg:` up, a sheet below.
 *
 * Two stores back it (see ui-shell-store.ts for why), so every control that
 * opens or closes the agent goes through here rather than choosing one.
 */
export function useAgentPanel(): { open: boolean; toggle: () => void; close: () => void } {
  const docked = useMediaQuery(MEDIA_AGENT_DOCKED);
  const overlay = useUiShellStore((state) => state.overlay);
  const agentColumn = useUiShellStore((state) => state.agentColumn);
  const setAgentColumn = useUiShellStore((state) => state.setAgentColumn);
  const toggleAgent = useUiShellStore((state) => state.toggleAgent);
  const closeOverlay = useUiShellStore((state) => state.closeOverlay);

  if (docked) {
    return {
      open: agentColumn,
      toggle: () => setAgentColumn(!agentColumn),
      close: () => setAgentColumn(false),
    };
  }
  return { open: overlay === "agent", toggle: toggleAgent, close: closeOverlay };
}
