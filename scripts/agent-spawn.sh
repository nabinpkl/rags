#!/usr/bin/env bash
# Spawn a persistent worker agent as an interactive claude in a PANE of the
# shared "agents" window, running in its OWN git worktree so worker git ops
# never collide with the coordinator (who stays on `main` in the primary repo)
# or with other workers. Pane is pinned to a known --session-id.
#
# Isolation:
#   - Each role gets a detached worktree at .worktrees/<role>, based on
#     AGENT_BASE (default origin/main). The implementor branches inside its
#     worktree; read-only roles just read the detached ref.
#   - Coordination state (run-files, task logs) lives in the PRIMARY repo's
#     .claude/run/ (absolute), so the coordinator sees it from `main`.
#   - The session jsonl is found by uuid (agent-feed.sh globs), so the worker's
#     cwd being a worktree doesn't hide it.
#
# Env knobs:
#   AGENT_BASE   git ref the worktree is detached at (default origin/main;
#                set to origin/<pr-branch> for the reviewer).
#   AGENT_MODEL  claude model for this worker (e.g. opus; default: account default).
#   TMUX_SESSION / AGENTS_WINDOW  targeting overrides.
#
# Usage: scripts/agent-spawn.sh <role> [task-file]   # prints the session uuid
set -euo pipefail

REPO="${ASKRAG_REPO:-/Users/nabin/projects/rags}"
SESSION="${TMUX_SESSION:-$(tmux ls -F '#{session_name}' 2>/dev/null | grep -E '^rags' | head -1)}"
WINDOW="${AGENTS_WINDOW:-agents}"
base="${AGENT_BASE:-origin/main}"
model="${AGENT_MODEL:-}"
role="${1:?usage: agent-spawn.sh <role> [task-file]}"
task="${2:-}"

if [ -z "$SESSION" ] || ! tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "FATAL: no pre-existing tmux session matching 'rags' (set TMUX_SESSION to override)." >&2
  echo "       Start the session yourself and retry; the harness will not create it." >&2
  exit 1
fi

brief="$REPO/.claude/briefs/$role.md"
[ -f "$brief" ] || { echo "no brief at $brief" >&2; exit 1; }
if [ -n "$task" ]; then
  [ -f "$task" ] || { echo "no task file at $task" >&2; exit 1; }
  # Absolutize: .claude/tasks/ is gitignored, so the task file lives ONLY in
  # the coordinator's primary checkout, not in the worker's worktree. A
  # relative path in the boot prompt would resolve against the worktree cwd
  # and miss it — the worker must read it by absolute path (same reason the
  # brief above is absolute).
  task="$(cd "$(dirname "$task")" && pwd)/$(basename "$task")"
fi

uuid="$(uuidgen | tr 'A-Z' 'a-z')"
RUN="$REPO/.claude/run"
mkdir -p "$RUN"
printf '%s\n' "$uuid" > "$RUN/$role.session"

# Fresh detached worktree for this role (drop any stale one first).
WT="$REPO/.worktrees/$role"
git -C "$REPO" fetch origin -q 2>/dev/null || true
if git -C "$REPO" worktree list --porcelain 2>/dev/null | grep -qx "worktree $WT"; then
  git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || true
fi
rm -rf "$WT" 2>/dev/null || true
git -C "$REPO" worktree add --detach "$WT" "$base" -q

# The worker reads its brief/task from the PRIMARY repo (absolute) so the labels
# are identical regardless of the worktree's ref.
boot="You are the $role in the askRAG SDLC loop. First read $brief. "
if [ -n "$task" ]; then
  boot+="Then read $task and execute exactly the task it describes, reporting back per your brief. "
else
  boot+="Then wait for the coordinator to send you a task. "
fi
boot+="You are in your own git worktree ($WT); branch/commit here freely. Work in the open: this pane is watched."

claude_cmd="claude --session-id $uuid"
[ -n "$model" ] && claude_cmd+=" --model $model"

# Respawn: kill this role's prior pane if alive.
oldpane="$(cat "$RUN/$role.pane" 2>/dev/null || true)"
if [ -n "$oldpane" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$oldpane"; then
  tmux kill-pane -t "$oldpane" 2>/dev/null || true
fi

# Add the worker as a pane in the shared agents window (cwd = its worktree).
if tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx "$WINDOW"; then
  pane="$(tmux split-window -t "$SESSION:$WINDOW" -c "$WT" -P -F '#{pane_id}' "$claude_cmd")"
else
  tmux new-window -d -t "$SESSION" -n "$WINDOW" -c "$WT" "$claude_cmd"
  pane="$(tmux list-panes -t "$SESSION:$WINDOW" -F '#{pane_id}' | head -1)"
  tmux set-window-option -t "$SESSION:$WINDOW" pane-border-status top >/dev/null 2>&1 || true
  tmux set-window-option -t "$SESSION:$WINDOW" pane-border-format " #{@role} " >/dev/null 2>&1 || true
fi
# @role user option survives the claude TUI overwriting pane_title.
tmux set -p -t "$pane" @role "$role" >/dev/null 2>&1 || true
tmux select-layout -t "$SESSION:$WINDOW" tiled >/dev/null 2>&1 || true
printf '%s\n' "$pane" > "$RUN/$role.pane"

sleep 2
"$(dirname "$0")/agent-send.sh" "$role" "$boot"

echo "$uuid"
