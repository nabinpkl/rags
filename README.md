# askRAG

Agentic RAG over a sample of arXiv CS: an agent side panel that feeds itself
with tools (hybrid retrieval, metadata SQL, paper reading, sandboxed Python,
UI driving) on a hand-built loop.

The corpus is 57,206 catalog rows, 20,733 of them with extracted text, and 667
chunked and embedded for retrieval — densest in July and August 2026 (94% and
49% of the cs papers arXiv posted those months) and a few papers a month
before that. It is a sample, never a census, and the landing page says so with
the catalog's own counts beside ours.

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
