# askRAG umbrella recipes — delegate into the per-part justfiles (spec §4c).
# Run `just` to list. Remaining backend/frontend recipes land with #11+/#26.
#
# Collector variable overrides pass through as args,
# e.g.  just diverse max_gb=8 permonth=5

collector := "collector/justfile"

# List recipes
default:
    @just --list

# Install/refresh the shared taste-plugin SDLC harness (agent-* scripts, the
# branch-protection hook, and the rendered role briefs). Run once per clone and
# after a plugin update. Source of truth: the nabin-ecc taste plugin.
harness-install:
    bash "${TASTE_HARNESS:-$HOME/projects/nabin-ecc/taste/scripts/harness}/harness-install.sh"

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

# Golden-set drafting (#17 fills this in): resolves in the uv workspace
# (issue #79) against the shared venv; a stub until draft_golden_set.py lands.
draft-evals:
    cd evals && uv run python -c "print('draft-evals: not implemented (#17)')"

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

# Dev server (#30): uvicorn serving the FastAPI chat API with autoreload.
# Extra args pass through to uvicorn, e.g. `just serve --port 8001`.
serve *ARGS:
    cd backend && uv run uvicorn askrag.api.app:app --reload --host 127.0.0.1 --port 8000 {{ARGS}}

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

# --- deployment (#81; D13) ------------------------------------------------
# compose lives in deploy/, so `docker compose -f deploy/compose.yml` picks up
# deploy/.env automatically (project dir = the compose file's dir).

# Build images and bring the stack up (ingress on 127.0.0.1 only)
deploy *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -f deploy/.env ]; then
        echo "deploy/.env missing — cp deploy/.env.example deploy/.env and fill it in" >&2
        exit 1
    fi
    docker compose -f deploy/compose.yml up -d --build {{ARGS}}
    docker compose -f deploy/compose.yml ps

# Stop the stack (volumes survive: traces.db and the chroma copy)
deploy-down *ARGS:
    docker compose -f deploy/compose.yml down {{ARGS}}

# Follow container logs
deploy-logs *ARGS:
    docker compose -f deploy/compose.yml logs -f {{ARGS}}

# Re-seed the chroma volume from the host snapshot — run after a re-ingest
# (D12: refreshing prod = new snapshot + restart), NOT part of a normal deploy
deploy-reseed:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose -f deploy/compose.yml down
    docker volume rm askrag_chroma
    just deploy

# Publish the loopback ingress onto the tailnet (tailnet HTTPS + MagicDNS).
# Needs the tailscale operator or sudo; idempotent.
deploy-tailnet:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; . deploy/.env; set +a
    ingress="${ASKRAG_INGRESS_PORT:-8420}"
    tsport="${ASKRAG_TAILNET_PORT:-8443}"
    tailscale serve --bg --https="$tsport" "http://127.0.0.1:${ingress}"
    host="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
    echo "askRAG is on the tailnet: https://${host}:${tsport}"

# Withdraw the tailnet listener (the stack keeps running on loopback)
deploy-tailnet-off:
    #!/usr/bin/env bash
    set -euo pipefail
    set -a; . deploy/.env; set +a
    tailscale serve --https="${ASKRAG_TAILNET_PORT:-8443}" off

# Backend tests only (pytest via uv; extra args pass through)
be-test *ARGS:
    cd backend && uv run pytest {{ARGS}}

# Thin alias kept for muscle memory; backend-check is the gate
alias be-lint := backend-check
