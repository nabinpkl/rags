#!/usr/bin/env bash
# Run BY a worker agent (from its own Bash) to launch a LONG-RUNNING command in
# a visible split pane inside its own tmux window, teeing output to a log. Use
# this only for long tasks whose progress should be watchable (ingest, embed,
# eval, test suites, benchmarks). Short commands stay in the agent's own Bash —
# do not spawn a pane per trivial command.
#
# The agent runs inside a tmux pane, so `tmux split-window` with no target hits
# the agent's current window. The command runs to completion, then the pane
# holds its final screen (remain-on-exit) so the outcome stays readable until
# the agent or human closes it.
#
# Usage: scripts/agent-pane.sh <label> <command...>
#   label       short name for the run (used for the log file)
#   command...  the long-running command and its args
# Prints the log path; the pane streams live and the log is the durable record.
set -euo pipefail

[ -n "${TMUX:-}" ] || { echo "not inside tmux — agent-pane.sh must be run by a tmux-hosted agent" >&2; exit 1; }
label="${1:?usage: agent-pane.sh <label> <command...>}"; shift
[ "$#" -ge 1 ] || { echo "no command given" >&2; exit 1; }

REPO="${REPO:-/Users/nabin/projects/rags}"
mkdir -p "$REPO/.claude/run"
log="$REPO/.claude/run/task-$label.log"

# Build a safely-quoted command string; tee to the log so the record outlives
# the pane. remain-on-exit keeps the final output on screen after it finishes.
cmd="$(printf '%q ' "$@")"
tmux split-window -v -c "$REPO" \
  "set -o pipefail; { $cmd; } 2>&1 | tee '$log'; echo \"[exit \$? — pane kept; close with Ctrl-b x]\""
tmux select-layout tiled >/dev/null 2>&1 || true

echo "$log"
