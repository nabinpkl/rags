#!/usr/bin/env bash
# Spawn a persistent worker agent as an INTERACTIVE claude in its own tmux
# window, pinned to a known session id so the coordinator knows exactly which
# jsonl to watch (no guessing the newest file).
#
# Observability contract:
#   - The tmux session is pre-existing and human-owned; we attach, never create.
#   - Human peeks/steers by attaching the session (Ctrl-b n/p to switch windows;
#     type to intervene, Ctrl-C to halt the current action).
#   - Coordinator drives via `tmux send-keys` and reads the session jsonl.
#   - Long-running task output is made visible by the agent via agent-pane.sh
#     (a split pane in its own window); short commands stay in the agent's Bash.
#   - Compaction-by-respawn: at a coherent task boundary the coordinator kills
#     the window and re-spawns fresh; durable context lives in the brief + PR +
#     the task file, not in the agent's head.
#
# Usage: scripts/agent-spawn.sh <role> [task-file]
#   role      = a brief under .claude/briefs/<role>.md (implementor|reviewer)
#   task-file = optional path the worker should read and execute
# Prints the pinned session uuid on stdout (the coordinator captures it).
set -euo pipefail

REPO="${REPO:-/Users/nabin/projects/rags}"
# The tmux session is PRE-EXISTING (the human owns its lifecycle). We attach to
# it, never create it. Default resolves the human's `rags` session (real name
# may be suffixed, e.g. rags-0, when it belongs to a session group).
SESSION="${TMUX_SESSION:-$(tmux ls -F '#{session_name}' 2>/dev/null | grep -E '^rags' | head -1)}"
role="${1:?usage: agent-spawn.sh <role> [task-file]}"
task="${2:-}"

# Fail loud if the session isn't there — a missing session is a broken
# precondition, not something to paper over by spawning a detached one.
if [ -z "$SESSION" ] || ! tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "FATAL: no pre-existing tmux session matching 'rags' (set TMUX_SESSION to override)." >&2
  echo "       Start the session yourself and retry; the harness will not create it." >&2
  exit 1
fi

brief="$REPO/.claude/briefs/$role.md"
[ -f "$brief" ] || { echo "no brief at $brief" >&2; exit 1; }
[ -n "$task" ] && { [ -f "$task" ] || { echo "no task file at $task" >&2; exit 1; }; }

uuid="$(uuidgen | tr 'A-Z' 'a-z')"
# Record the pinned id so `agent-feed.sh <role>` can find this run's jsonl
# without the human pasting a uuid. One file per role, overwritten on respawn.
mkdir -p "$REPO/.claude/run"
printf '%s\n' "$uuid" > "$REPO/.claude/run/$role.session"

# Short, robust bootstrap; the heavy context stays in files the worker reads,
# so we never have to shove a multi-KB prompt through tmux send-keys.
boot="You are the $role in the askRAG SDLC loop. First read $brief. "
if [ -n "$task" ]; then
  boot+="Then read $task and execute exactly the task it describes, reporting back per your brief. "
else
  boot+="Then wait for the coordinator to send you a task. "
fi
boot+="Work in the open: this window is watched."

# One window per agent inside the pre-existing session (each agent's TUI needs
# a full canvas; long-running task output splits into a pane WITHIN this window,
# via agent-pane.sh). Replace any stale window for this role (respawn semantics).
tmux kill-window -t "$SESSION:$role" 2>/dev/null || true
# -d: create detached so we don't yank the human's attached view to this window.
tmux new-window -d -t "$SESSION" -n "$role" -c "$REPO" "claude --session-id $uuid"

# Let the TUI come up, then deliver the bootstrap via the shared sender (which
# waits for the input to settle before pressing Enter — see agent-send.sh).
sleep 2
"$(dirname "$0")/agent-send.sh" "$role" "$boot"

echo "$uuid"
