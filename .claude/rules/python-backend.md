---
paths:
  - "backend/**"
  - "collector/**"
---

# Python / FastAPI idiom — askRAG residue

The binding idioms now live in the taste plugin, one home each:
**taste:web-stack** (Python + FastAPI deltas: uv/ruff/ty, no bare dicts, `Depends`
in lifespan, `async def` only for awaiting paths, `response_model`, state
machines over boolean soup) and **taste:code-organization** (absolute imports,
custom errors with a preserved chain, pytest fixtures/`tmp_path`/`parametrize`,
scope-guard resource ownership, tests mirroring source names 1:1). Idiomatic by
default; a deviation needs a `DECISIONS.md` entry (what, why, revisit trigger) in
the same PR — no human sign-off. Undocumented non-idiom is a review finding.

Only askRAG-specific facts live here:

- **Gate**: `just backend-check` before any handoff (ruff check, ruff
  format --check, ty, fast tests); `just check` runs backend + frontend together.
- **Tunables home**: every tunable reads from `backend/askrag/config.py`, never a
  module literal (this is a house rule, stronger than idiom).
- **SSE vocabulary**: event names come only from `askrag/api/sse_events.py`; the
  frontend `lib/sse.ts` mirrors it under test. Do not spell an event name inline.
