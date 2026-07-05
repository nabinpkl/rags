---
paths:
  - "backend/**"
  - "collector/**"
---

# Python / FastAPI idiom — default posture

Idiomatic by default. A deviation needs a `decisions.md` entry (what, why,
revisit trigger) in the same PR — no human sign-off. Non-idiomatic code
without a logged decision is a review finding.

## Python

- Type hints on every public function; pyright stays clean. `pathlib` over
  `os.path`, f-strings, `dataclasses`/pydantic models over dict-shaped data
  crossing any boundary, `Enum`/`Literal` over bare string constants for
  closed sets.
- Exceptions over sentinel returns: raise narrow types, catch narrowly,
  never bare `except`. A broken invariant raises; no silent fallbacks.
- Resources (connections, files, subprocesses) are owned by context
  managers, not paired open/close calls.
- Module constants only for protocol facts; anything tunable reads from
  `config.py` (house rule, not just idiom).
- pytest idiom: fixtures over setup methods, `tmp_path` over hand-rolled
  temp dirs, `parametrize` over copy-pasted cases.

## FastAPI (when routes exist)

- Pydantic request/response models — no raw dicts on the wire;
  `response_model` explicit on every route.
- Shared resources arrive via `Depends`, created in the lifespan context,
  never at import time.
- `async def` only for genuinely awaiting paths; sync work (SQLite calls)
  stays `def` so it runs in the threadpool instead of blocking the loop.
- One router per resource, mounted in `app.py`; SSE via sse-starlette
  generators, event names only from `sse_events.py`.

## State

- State machines over boolean soup: three or more interacting flags become
  one explicit state enum with named transitions (agent loop phases, budget
  states, run lifecycle). Illegal states unrepresentable beats runtime
  checks.
