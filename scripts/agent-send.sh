#!/usr/bin/env bash
# Send a SHORT control message to a tmux-hosted worker and submit it. Types the
# text, waits for the TUI to settle, then presses Enter as a separate key —
# sending Enter immediately after the text leaves it typed-but-unsubmitted
# (Claude Code debounces pasted input). Used for the boot prompt and for the
# coordinator relaying instructions to a running worker.
#
# Keep messages short. Big context (task specs, review findings) goes in a file
# or a PR comment; send a one-line "read <path> and act" instead of typing
# kilobytes through tmux.
#
# Usage: scripts/agent-send.sh <role> <message...>
set -euo pipefail

SESSION="${TMUX_SESSION:-$(tmux ls -F '#{session_name}' 2>/dev/null | grep -E '^rags' | head -1)}"
role="${1:?usage: agent-send.sh <role> <message...>}"; shift
msg="$*"
[ -n "$msg" ] || { echo "empty message" >&2; exit 1; }

[ -n "$SESSION" ] && tmux has-session -t "$SESSION" 2>/dev/null \
  || { echo "FATAL: no pre-existing 'rags' tmux session" >&2; exit 1; }
tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx "$role" \
  || { echo "FATAL: no window '$role' in $SESSION (spawn it first)" >&2; exit 1; }

# Target the window by name so the human's focus isn't yanked. -l = literal text.
tmux send-keys -t "$SESSION:$role" -l "$msg"
sleep 1.2   # let the TUI absorb the input before submitting
tmux send-keys -t "$SESSION:$role" Enter
