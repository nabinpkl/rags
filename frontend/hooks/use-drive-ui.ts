"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";

/** The bridge from confirmed agent actions to what the reader sees (D-2,
 * DECISIONS.md, issue #32). `agent-session-store.ts` must not import either
 * destination (one authoritative home per fact, stores stay decoupled); this
 * hook is the thin, framework-bound wiring in between.
 *
 * Each action goes to the owner of the thing it changes: `open_paper` and
 * `goto_page` to viewer-store, and `set_filters` to the URL, which is the
 * list filter's only home (use-catalog-query.ts). Writing the filter into a
 * store nothing renders from would confirm the tool call and change nothing
 * on screen.
 *
 * Subscribes to `confirmedUiActions` by reference: that array is a new
 * reference only when a ui_action's paired tool_result_summary confirms
 * ok=true or when this effect drains it, so each confirmation applies
 * exactly once, never on an unrelated update such as streamed answer text.
 *
 * Mounted once on the demo route, the one component spanning both the list
 * and the reader. */
export function useDriveUi(): void {
  const confirmedUiActions = useAgentSessionStore((state) => state.confirmedUiActions);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (confirmedUiActions.length === 0) return;
    const actions = useAgentSessionStore.getState().drainConfirmedUiActions();
    const { applyDriveAction } = useViewerStore.getState();
    for (const action of actions) {
      if (action.action === "set_filters") {
        // Back to the list, filtered: dropping `paper` is what leaves the
        // reader. Only a key the model actually sent is touched; an omitted
        // key means "no change", not "clear".
        const next = new URLSearchParams(searchParams);
        next.delete("paper");
        next.delete("page");
        if ("category" in action.args) {
          const category = action.args.category;
          if (typeof category === "string") next.set("category", category);
          else next.delete("category");
        }
        const qs = next.toString();
        router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
      } else {
        applyDriveAction(action.action, action.args);
      }
    }
    // On a narrow viewport the agent panel is a sheet COVERING the region it
    // just drove (#83). Docked, there is no overlay and this is a no-op.
    useUiShellStore.getState().closeOverlay();
  }, [confirmedUiActions, pathname, router, searchParams]);
}
