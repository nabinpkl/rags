# askRAG umbrella recipes — delegate into the per-part justfiles (spec §4c).
# Run `just` to list. Remaining backend/frontend recipes land with #11+/#26.
#
# Collector variable overrides pass through as args,
# e.g.  just diverse max_gb=8 permonth=5

collector := "collector/justfile"

# List recipes
default:
    @just --list

# One-time collector setup: uv-managed environment + dependencies
setup *ARGS:
    @just --justfile {{collector}} {{ARGS}} setup

# Collector Part 1 — most recent papers (newest-first, exact budget)
latest *ARGS:
    @just --justfile {{collector}} {{ARGS}} latest

# Collector Part 1 — temporal sample (N per month, all years)
sample *ARGS:
    @just --justfile {{collector}} {{ARGS}} sample

# Collector Part 1 — diverse spread (blended-facet score, all years)
diverse *ARGS:
    @just --justfile {{collector}} {{ARGS}} diverse

# Collector Part 1 — bulk backfill from a date (Kaggle seed + GCS mirror)
backfill *ARGS:
    @just --justfile {{collector}} {{ARGS}} seeded-backfill

# Collector Part 2 — incremental pull via OAI-PMH
update *ARGS:
    @just --justfile {{collector}} {{ARGS}} oai-update

# Show collector store stats and the incremental watermark
status *ARGS:
    @just --justfile {{collector}} {{ARGS}} status

# Backend gate before any handoff: lint, format, types (ty), fast tests
backend-check:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest -q

# Frontend gate: lint + typecheck + tests + generated-types drift check.
# CI installs deps first (see ci.yml); locally, run `pnpm install` in frontend/ once.
frontend-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d frontend ]; then
        echo "frontend not scaffolded yet, skipping"
        exit 0
    fi
    cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm gen:api:check

# Full-repo gate — CI runs exactly this, so local green == CI green
check: backend-check frontend-check

# Spine checkpoint (#16): hybrid retrieval over the real corpus.
# Both call forms work: `just ask q="chain of thought"` / `just ask "chain of thought"`
ask *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    # Recipe args arrive via interpolation ({{ARGS}}), never via shell $*.
    query={{quote(ARGS)}}
    query="${query#q=}"
    cd backend && uv run python -m askrag.retrieval.hybrid_search "$query"

# Terminal REPL (#24), milestone 3's exit artifact: interactive multi-turn
# agent loop with a live tool timeline and running session cost. `q="..."`
# runs a single one-shot turn instead of the interactive prompt (same call
# forms as `ask`); bare `just repl` starts the interactive REPL.
repl *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    question={{quote(ARGS)}}
    question="${question#q=}"
    cd backend && if [ -z "$question" ]; then uv run python -m askrag.cli; else uv run python -m askrag.cli "$question"; fi

# Agent loop smoke (#23/#24): cheap-first validation via OpenRouter before
# spending on Haiku. Needs ASKRAG_AGENT_API_BASE_URL=https://openrouter.ai/api
# (no trailing /v1 — the anthropic SDK appends /v1/messages itself) and
# OPENROUTER_API_KEY in backend/.env. Both call forms work, same as `ask`.
smoke-agent *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    question={{quote(ARGS)}}
    question="${question#q=}"
    cd backend && uv run python -m askrag.cli "$question"

# Backend tests only (pytest via uv; extra args pass through)
be-test *ARGS:
    cd backend && uv run pytest {{ARGS}}

# Thin alias kept for muscle memory; backend-check is the gate
alias be-lint := backend-check
