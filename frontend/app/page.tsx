import { Suspense } from "react";
import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { ExplorerPanel } from "@/components/explorer/explorer-panel";

// The single app shell (§4c decision 2: one page, no dynamic routes — a paper
// is a `?paper=<id>` search param, never a `/papers/[id]` route). The viewer
// (#29) is a third region between explorer and agent panel; this issue
// mounts explorer + agent panel two-up. `Suspense` is required around
// ExplorerPanel because it (via use-viewer-url-sync.ts) calls
// `useSearchParams`, which Next's static export build requires to be
// wrapped in a boundary.
export default function Home() {
  return (
    <main className="flex h-screen flex-col md:flex-row">
      <div className="min-w-0 flex-1">
        <Suspense fallback={null}>
          <ExplorerPanel />
        </Suspense>
      </div>
      <div className="h-full w-full md:w-[420px]">
        <ChatPanel />
      </div>
    </main>
  );
}
