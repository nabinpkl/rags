"use client";

import { useEffect } from "react";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useViewerStore } from "@/stores/viewer-store";

/** The agent-session-store <-> viewer-store bridge (D-2, DECISIONS.md, issue
 * #32) — mirrors use-viewer-url-sync.ts's role bridging store<->URL.
 * `agent-session-store.ts` must not import `viewer-store.ts` (frontend
 * rules: one authoritative home per fact, stores stay decoupled); this hook
 * is the thin, framework-bound wiring in between.
 *
 * Subscribes to `confirmedUiActions` by reference: that array is a new
 * reference only when a ui_action's paired tool_result_summary confirms
 * ok=true (agent-session-store.ts) or when this effect drains it — so the
 * effect fires exactly on a new confirmation, never on an unrelated
 * agent-session-store update (e.g. streamed answer text), satisfying "drain
 * exactly once, don't re-apply on every store update."
 *
 * Mounted once in AppRegion (app/page.tsx), the one component spanning both
 * the explorer and viewer regions. */
export function useDriveUi(): void {
  const confirmedUiActions = useAgentSessionStore((state) => state.confirmedUiActions);

  useEffect(() => {
    if (confirmedUiActions.length === 0) return;
    const actions = useAgentSessionStore.getState().drainConfirmedUiActions();
    const { applyDriveAction } = useViewerStore.getState();
    for (const action of actions) {
      applyDriveAction(action.action, action.args);
    }
  }, [confirmedUiActions]);
}
