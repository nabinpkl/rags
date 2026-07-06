#!/usr/bin/env bash
# Send a SHORT control message to a tmux-hosted worker's pane and submit it.
# Types the text, waits for the TUI to settle, then presses Enter as a separate
# key — sending Enter immediately after the text leaves it typed-but-unsubmitted
# (Claude Code debounces pasted input). Used for the boot prompt and for the
# coordinator relaying instructions to a running worker.
#
# Keep messages short. Big context (task specs, review findings) goes in a file
# or a PR comment; send a one-line "read <path> and act" instead of typing
# kilobytes through tmux.
#
# Usage: scripts/agent-send.sh <role> <message...>
set -euo pipefail

REPO="${ASKRAG_REPO:-/Users/nabin/projects/rags}"
role="${1:?usage: agent-send.sh <role> <message...>}"; shift
msg="$*"
[ -n "$msg" ] || { echo "empty message" >&2; exit 1; }

# Target the worker's specific pane (recorded by agent-spawn.sh), since many
# workers share one window and send-keys to a window hits only its active pane.
pane="$(cat "$REPO/.claude/run/$role.pane" 2>/dev/null || true)"
[ -n "$pane" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$pane" \
  || { echo "FATAL: no live pane for role '$role' (spawn it first)" >&2; exit 1; }

tmux send-keys -t "$pane" -l "$msg"
sleep 1.2   # let the TUI absorb the input before submitting
tmux send-keys -t "$pane" Enter
