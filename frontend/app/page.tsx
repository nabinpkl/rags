import { ChatPanel } from "@/components/agent-panel/chat-panel";

// The single app shell (§4c decision 2: one page, no dynamic routes — a paper
// is a `?paper=<id>` search param, never a `/papers/[id]` route). The
// explorer + viewer 3-column composition lands in a later issue; this
// mounts the agent panel standalone, full-height, so the slice demos
// end-to-end against `just serve`.
export default function Home() {
  return (
    <main className="flex h-screen flex-col md:flex-row">
      <div className="flex-1 overflow-y-auto p-8">
        <h1 className="font-sans text-2xl font-semibold">askRAG</h1>
        <p className="mt-2 text-sm">
          Agentic RAG over 6,460 arXiv CS papers. Explorer and viewer land in a later issue — this
          is the agent panel, wired end-to-end against <code>just serve</code>.
        </p>
      </div>
      <div className="h-full w-full md:w-[420px]">
        <ChatPanel />
      </div>
    </main>
  );
}
