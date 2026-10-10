"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect } from "react";

import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { CatalogView } from "@/components/catalog/catalog-view";
import { AgentButton } from "@/components/shell/agent-button";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { PaperSplitView } from "@/components/viewer/paper-split-view";
import { useAgentPanel } from "@/hooks/use-agent-panel";
import { useDriveUi } from "@/hooks/use-drive-ui";
import { useViewerUrlSync } from "@/hooks/use-viewer-url-sync";
import { agentEnabled } from "@/lib/agent-flag";
import { fetchCatalogFacets } from "@/lib/api-client";
import { useAgentSessionStore } from "@/stores/agent-session-store";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";

/** The RAG demo: the indexed papers, and an agent that knows those papers
 * and no others — a STATIC route (§4c decision 2), a paper is `?paper=<id>`,
 * never a `/papers/[id]` segment.
 *
 * The list is Explore's, with the scope pinned to what the agent can read
 * (D16). The pin is the client's half; the server's half is that every agent
 * tool reads `chunks` or applies INDEXED_PREDICATE, so a paper absent from
 * this list is absent from the agent too, whatever the model asks for.
 *
 * The chat is not scoped to the rail's filter. Narrowing the list to cs.CR
 * does not shrink the agent's corpus to nine papers; the model can narrow
 * itself through `search_corpus`'s own category argument when a question
 * calls for it.
 */
export default function DemoPage() {
  return (
    // `useSearchParams` needs a boundary in a static export build.
    <Suspense fallback={null}>
      <Demo />
    </Suspense>
  );
}

function Demo() {
  // Both hooks live here because this component spans the list and the
  // reader and never unmounts across the swap between them: an owner that
  // unmounted on the very store change it reacts to would drop that change's
  // URL push (DECISIONS.md, #28/#29).
  useViewerUrlSync();
  useDriveUi();

  const params = useSearchParams();
  const paper = useViewerStore((state) => state.paper);
  const overlay = useUiShellStore((state) => state.overlay);
  const agentColumn = useUiShellStore((state) => state.agentColumn);
  const agentPanel = useAgentPanel();

  // A transcript started under a landing-page claim is about that claim's
  // papers. Shown here, under an agent that reads all of them, it would put
  // one scope's answers under another's heading.
  useEffect(() => {
    const session = useAgentSessionStore.getState();
    if (session.turns.length > 0 && session.scope !== null) session.reset();
  }, []);

  // The unfiltered count, for the agent's boundary line. Same key as the
  // list's facets query at rest, so the two share one request.
  const { data: scopeFacets } = useQuery({
    queryKey: ["catalog-facets", undefined, undefined, undefined, "indexed"],
    queryFn: () => fetchCatalogFacets({ holding: "indexed" }),
  });
  const paperCount = scopeFacets?.holdings.find((bucket) => bucket.value === "indexed")?.papers;

  // In place, carrying the filter: closing the paper returns to this list.
  const readerHref = useCallback(
    (arxivId: string) => {
      const next = new URLSearchParams(params);
      next.delete("page");
      next.set("paper", arxivId);
      return `/demo?${next.toString()}`;
    },
    [params],
  );

  return (
    <CatalogView
      view="demo"
      pinnedHolding="indexed"
      heading={{ title: "RAG Demo", subtitle: "Subset of CS papers that are indexed for the demo." }}
      readerHref={readerHref}
      barEnd={agentEnabled() ? <AgentButton /> : undefined}
      reader={paper ? <PaperSplitView /> : undefined}
      aside={
        agentEnabled() && (
        // On demand at every width: the sheet follows the overlay below
        // `lg:`, the column follows its own flag above it, and the one
        // ChatPanel stays mounted through both (it owns the SSE stream).
        <DrawerPanel
          dockAt="lg"
          side="right"
          id="agent-panel"
          label="Agent panel"
          open={overlay === "agent"}
          dockedOpen={agentColumn}
          onClose={agentPanel.close}
          className="w-full sm:w-[420px] lg:h-full lg:w-[420px] lg:shrink-0"
        >
          <ChatPanel paperCount={paperCount} onClose={agentPanel.close} />
        </DrawerPanel>
        )
      }
    />
  );
}
