#!/usr/bin/env bash
# Spawn a persistent worker agent as an interactive claude in a PANE of a single
# shared "agents" window inside the human's pre-existing tmux session — a tiled
# grid so every worker is visible at once, no window switching. The pane is
# pinned to a known --session-id, so the coordinator knows exactly which jsonl
# to read, and its id is recorded so agent-send.sh can target it.
#
# Observability contract:
#   - The tmux session is pre-existing and human-owned; we attach, never create.
#   - Human peeks/steers by viewing the agents window (all panes tiled); type to
#     intervene in a pane, Ctrl-C to halt its current action.
#   - Coordinator drives via agent-send.sh (targets the pane) and reads the jsonl.
#   - Long-running task output is made visible by the agent via agent-pane.sh
#     (a further split); short commands stay in the agent's Bash.
#   - Compaction-by-respawn: at a task boundary the coordinator kills the pane
#     and re-spawns; durable context lives in the brief + PR + task file.
#
# Usage: scripts/agent-spawn.sh <role> [task-file]
# Prints the pinned session uuid on stdout.
set -euo pipefail

REPO="${REPO:-/Users/nabin/projects/rags}"
SESSION="${TMUX_SESSION:-$(tmux ls -F '#{session_name}' 2>/dev/null | grep -E '^rags' | head -1)}"
WINDOW="${AGENTS_WINDOW:-agents}"
role="${1:?usage: agent-spawn.sh <role> [task-file]}"
task="${2:-}"

if [ -z "$SESSION" ] || ! tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "FATAL: no pre-existing tmux session matching 'rags' (set TMUX_SESSION to override)." >&2
  echo "       Start the session yourself and retry; the harness will not create it." >&2
  exit 1
fi

brief="$REPO/.claude/briefs/$role.md"
[ -f "$brief" ] || { echo "no brief at $brief" >&2; exit 1; }
[ -n "$task" ] && { [ -f "$task" ] || { echo "no task file at $task" >&2; exit 1; }; }

uuid="$(uuidgen | tr 'A-Z' 'a-z')"
RUN="$REPO/.claude/run"
mkdir -p "$RUN"
printf '%s\n' "$uuid" > "$RUN/$role.session"

boot="You are the $role in the askRAG SDLC loop. First read $brief. "
if [ -n "$task" ]; then
  boot+="Then read $task and execute exactly the task it describes, reporting back per your brief. "
else
  boot+="Then wait for the coordinator to send you a task. "
fi
boot+="Work in the open: this pane is watched."

# Respawn: kill this role's prior pane if it is still alive.
oldpane="$(cat "$RUN/$role.pane" 2>/dev/null || true)"
if [ -n "$oldpane" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$oldpane"; then
  tmux kill-pane -t "$oldpane" 2>/dev/null || true
fi

# Add the worker as a pane in the shared agents window: split it if the window
# exists, else create the window (this role becomes its first pane).
if tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx "$WINDOW"; then
  pane="$(tmux split-window -t "$SESSION:$WINDOW" -c "$REPO" -P -F '#{pane_id}' "claude --session-id $uuid")"
else
  tmux new-window -d -t "$SESSION" -n "$WINDOW" -c "$REPO" "claude --session-id $uuid"
  pane="$(tmux list-panes -t "$SESSION:$WINDOW" -F '#{pane_id}' | head -1)"
  # A titled border per pane so the human can tell workers apart.
  tmux set-window-option -t "$SESSION:$WINDOW" pane-border-status top >/dev/null 2>&1 || true
  tmux set-window-option -t "$SESSION:$WINDOW" pane-border-format " #{pane_title} " >/dev/null 2>&1 || true
fi
tmux select-pane -t "$pane" -T "$role" >/dev/null 2>&1 || true
tmux select-layout -t "$SESSION:$WINDOW" tiled >/dev/null 2>&1 || true
printf '%s\n' "$pane" > "$RUN/$role.pane"

# Let the TUI come up, then deliver the bootstrap via the shared sender.
sleep 2
"$(dirname "$0")/agent-send.sh" "$role" "$boot"

echo "$uuid"
