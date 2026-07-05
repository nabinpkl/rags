# askRAG umbrella recipes — delegate into the per-part justfiles (spec §4c).
# Run `just` to list. backend/ and frontend/ recipes land with issues #10/#26.
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
