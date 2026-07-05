# askRAG

Agentic RAG over 6,460 arXiv CS papers: an agent side panel that feeds itself
with tools (hybrid retrieval, metadata SQL, paper reading, sandboxed Python,
UI driving) on a hand-built loop.

- **Design spec (source of truth):**
  [`docs/superpowers/specs/2026-07-04-agentic-rag-design.md`](docs/superpowers/specs/2026-07-04-agentic-rag-design.md)
- **Architecture map:** [`docs/architecture.html`](docs/architecture.html)
- **Collector (Part 0, corpus acquisition):** [`collector/`](collector/) —
  see its [README](collector/README.md); data artifacts live in `corpus/`
  (gitignored).
- **Work board:** issues on this repo,
  [project board](https://github.com/users/nabinpkl/projects/2).

`backend/` and `frontend/` land per the spec's milestones; this README grows
into the portfolio front door (pitch, eval table) as they do.
