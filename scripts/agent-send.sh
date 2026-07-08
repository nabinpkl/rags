#!/usr/bin/env bash
# Send a SHORT control message to a tmux-hosted worker's pane and CONFIRM it
# submitted. Naively typing text + sleeping + pressing Enter races the Claude
# TUI: during a slow boot (Opus especially) the Enter is swallowed and the
# message sits typed-but-unsubmitted, or the text is lost before the input is
# ready — either way the worker silently never starts. This script closes both
# by observing the pane's input box and retrying, then FAILS LOUD if the message
# never lands+submits (a silent no-send is the bug this exists to prevent).
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

# True while the TUI input box (the `❯` prompt line) holds unsubmitted text:
# grab the last `❯` line, strip the prompt, report whether anything remains.
# Empty input => the message submitted (or was never typed); non-empty => it's
# still pending in the box.
_input_pending() {
  tmux capture-pane -p -t "$pane" 2>/dev/null \
    | grep '❯' | tail -1 \
    | sed -E 's/^[[:space:]]*❯[[:space:]]?//' \
    | grep -qE '[^[:space:]]'
}

# Phase 1: get the text INTO the input box. A slow-booting TUI can drop the
# first keystrokes entirely (nothing lands), so re-type until the box is
# non-empty. Clear first (C-u) so a re-type can't double the message.
landed=0
for _ in $(seq 1 8); do
  tmux send-keys -t "$pane" C-u
  tmux send-keys -t "$pane" -l "$msg"
  sleep 1.0
  if _input_pending; then landed=1; break; fi
done
[ "$landed" = 1 ] || { echo "FATAL: text never landed in '$role' input (TUI not accepting input)" >&2; exit 1; }

# Phase 2: submit and confirm the box cleared. Re-press Enter if the first was
# swallowed mid-boot; fail loud if it never takes.
submitted=0
for _ in $(seq 1 6); do
  tmux send-keys -t "$pane" Enter
  sleep 1.0
  if ! _input_pending; then submitted=1; break; fi
  sleep 0.5
done
[ "$submitted" = 1 ] || { echo "FATAL: '$role' message typed but never submitted (TUI stuck)" >&2; exit 1; }
