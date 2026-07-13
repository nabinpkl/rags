---
paths:
  - "backend/**"
  - "collector/**"
---

# Python / FastAPI idiom — default posture

Idiomatic by default. A deviation needs a `DECISIONS.md` entry (what, why,
revisit trigger) in the same PR — no human sign-off. Non-idiomatic code
without a logged decision is a review finding.

## Toolchain (the Astral trio + just)

- **uv** owns environments and deps; **ruff** owns lint + format; **ty**
  owns type checking. No pyright, no mypy, no pip — one vendor, one speed
  profile. All three run in CI and in `just backend-check`.
- `just backend-check` is the gate before any handoff: ruff check, ruff
  format --check, ty, fast tests. `just check` runs backend and frontend
  checks together; run the side-specific one when only one side changed.

## Python

- Type hints on every public function; ty stays clean. `pathlib` over
  `os.path`, f-strings, `Enum`/`Literal` over bare string constants for
  closed sets.
- **No bare dicts as data.** Structured data crossing any boundary
  (function return, file format, wire, queue) is a frozen dataclass or a
  pydantic model — dicts are for genuinely open key-value maps only.
- **Imports: absolute always** (`from askrag.ingest import ...`), even
  inside the package; no relative imports.
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
