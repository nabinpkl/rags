"use client";

import { Suspense } from "react";
import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { ExplorerPanel } from "@/components/explorer/explorer-panel";
import { PaperSplitView } from "@/components/viewer/paper-split-view";
import { useViewerUrlSync } from "@/hooks/use-viewer-url-sync";
import { useViewerStore } from "@/stores/viewer-store";

/** Explorer <-> viewer swap (#29): `viewer-store`'s `paper` (URL-synced,
 * `?paper=`) picks which region renders. This is the ONE place
 * `useViewerUrlSync()` is called — it must live on a component that never
 * unmounts across the swap, since `explorer-panel.tsx` and
 * `paper-split-view.tsx` mount/unmount as `paper` toggles. Owning the sync
 * on either of THOSE would mean a row click's `setPaper` unmounts the sync
 * owner in the same commit that was supposed to push the new `?paper=` URL,
 * dropping the push entirely — the same class of race #28's cross-tick
 * carry-over note (decisions.md) warns about, one level up. */
function AppRegion() {
  useViewerUrlSync();
  const paper = useViewerStore((state) => state.paper);
  return paper ? <PaperSplitView /> : <ExplorerPanel />;
}

// The single app shell (§4c decision 2: one page, no dynamic routes — a paper
// is a `?paper=<id>` search param, never a `/papers/[id]` route). `Suspense`
// is required around AppRegion because it (via use-viewer-url-sync.ts) calls
// `useSearchParams`, which Next's static export build requires to be
// wrapped in a boundary.
export default function Home() {
  return (
    <main className="flex h-screen flex-col md:flex-row">
      <div className="min-w-0 flex-1">
        <Suspense fallback={null}>
          <AppRegion />
        </Suspense>
      </div>
      <div className="h-full w-full md:w-[420px]">
        <ChatPanel />
      </div>
    </main>
  );
}
