#!/usr/bin/env bash
# Run BY a worker agent (from its own Bash) to launch a LONG-RUNNING command in
# a visible split pane inside its own tmux window, teeing output to a log the
# coordinator can watch. Use only for long tasks whose progress should be
# visible (ingest, embed, eval, full test suites, benchmarks); short commands
# stay in the agent's Bash.
#
# The command runs in the worker's current directory (its git worktree). The log
# is written to the PRIMARY repo's .claude/run/ (absolute) so the coordinator,
# sitting on `main` in the primary repo, can tail it.
#
# Usage: scripts/agent-pane.sh <label> <command...>   # prints the log path
set -euo pipefail

[ -n "${TMUX:-}" ] || { echo "not inside tmux — agent-pane.sh must be run by a tmux-hosted agent" >&2; exit 1; }
label="${1:?usage: agent-pane.sh <label> <command...>}"; shift
[ "$#" -ge 1 ] || { echo "no command given" >&2; exit 1; }

REPO="${ASKRAG_REPO:-/Users/nabin/projects/rags}"
cwd="$PWD"                          # the worker's worktree
mkdir -p "$REPO/.claude/run"
log="$REPO/.claude/run/task-$label.log"

cmd="$(printf '%q ' "$@")"
tmux split-window -v -c "$cwd" \
  "set -o pipefail; { $cmd; } 2>&1 | tee '$log'; echo \"[exit \$? — pane kept; close with Ctrl-b x]\""
tmux select-layout tiled >/dev/null 2>&1 || true

echo "$log"
