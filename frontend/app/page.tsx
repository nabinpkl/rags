// The single app shell (§4c decision 2: one page, no dynamic routes — a paper
// is a `?paper=<id>` search param, never a `/papers/[id]` route). The explorer
// + viewer + agent-panel composition lands in later issues; this scaffold
// renders a placeholder so the static export builds and serves.
export default function Home() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="font-sans text-2xl font-semibold">askRAG</h1>
      <p className="mt-2 text-sm">
        Agentic RAG over 6,460 arXiv CS papers. Frontend scaffold — explorer, viewer, and agent
        panel land in later issues.
      </p>
    </main>
  );
}
