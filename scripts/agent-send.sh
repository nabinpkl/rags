#!/usr/bin/env bash
# Send a SHORT control message to a tmux-hosted worker's pane and CONFIRM it
# landed, without false alarms. Two real failure modes exist and this closes
# both without confusing them:
#   - genuine no-send: the message sits in the composer, agent idle (a modal or
#     a swallowed keystroke) — must FAIL LOUD.
#   - queued-behind-work: the agent is mid-turn; the message is accepted and
#     QUEUED, the composer clears when the turn ends — must SUCCEED, not FATAL.
# The old heuristic ("the ❯ box has any text") conflated these and false-FATAL'd
# whenever the agent went straight to work. This version keys on OUR text on the
# composer line and on whether a turn is actually running ("esc to interrupt").
#
# Keep messages short. Big context (task specs, review findings) goes in a file
# or a PR comment; send a one-line "read <path> and act" instead.
#
# Usage: scripts/agent-send.sh <role> <message...>
set -euo pipefail

REPO="${ASKRAG_REPO:-/Users/nabin/projects/rags}"
role="${1:?usage: agent-send.sh <role> <message...>}"; shift
msg="$*"
[ -n "$msg" ] || { echo "empty message" >&2; exit 1; }

pane="$(cat "$REPO/.claude/run/$role.pane" 2>/dev/null || true)"
[ -n "$pane" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$pane" \
  || { echo "FATAL: no live pane for role '$role' (spawn it first)" >&2; exit 1; }

# A distinctive snippet of the message to locate it on the composer line. The
# composer is the `❯` prompt line; after submit/queue our text leaves it (the
# submitted message moves up into the transcript), so "snippet still on the ❯
# line" == still pending in the box.
snippet="$(printf '%s' "$msg" | tr -s '[:space:]' ' ' | cut -c1-24)"
_composer_has_snippet() {
  tmux capture-pane -p -t "$pane" 2>/dev/null | grep '❯' | tail -1 | grep -qF "$snippet"
}
# A turn is actively running iff the pane shows the interrupt hint. (The token
# counter shows even at idle, so it is NOT a working signal.)
_working() { tmux capture-pane -p -t "$pane" 2>/dev/null | grep -qi 'esc to interrupt'; }

# Phase 1: get the text INTO the composer. A cold TUI can drop the first
# keystrokes; re-type (clearing first) until our snippet appears. ~15s window.
tmux send-keys -t "$pane" -l "$msg"
landed=0
for _ in $(seq 1 10); do
  sleep 1.5
  if _composer_has_snippet; then landed=1; break; fi
  tmux send-keys -t "$pane" C-u
  tmux send-keys -t "$pane" -l "$msg"
done
[ "$landed" = 1 ] || { echo "FATAL: text never landed in '$role' composer (TUI not accepting input)" >&2; exit 1; }

# Phase 2: submit and confirm the composer cleared OUR text. Press Enter once,
# then re-press only when the agent looks idle (re-pressing into a busy agent
# risks inserting newlines instead of submitting). ~30s window.
tmux send-keys -t "$pane" Enter
submitted=0
for _ in $(seq 1 20); do
  sleep 1.5
  if ! _composer_has_snippet; then submitted=1; break; fi
  _working || tmux send-keys -t "$pane" Enter
done
[ "$submitted" = 1 ] && exit 0

# Composer still holds our text. If a turn is running, it is queued behind that
# work and will send when the turn ends — success, not failure. Only a stuck
# composer with an IDLE agent is the real bug.
if _working; then
  echo "NOTE: '$role' message queued behind an active turn; it will send when that turn ends." >&2
  exit 0
fi
echo "FATAL: '$role' message typed but never submitted and the agent is idle (TUI stuck)" >&2
exit 1
