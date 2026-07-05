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

# Backend tests only (pytest via uv; extra args pass through)
be-test *ARGS:
    cd backend && uv run pytest {{ARGS}}

# Thin alias kept for muscle memory; backend-check is the gate
alias be-lint := backend-check
