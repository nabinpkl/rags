#!/usr/bin/env bash
# Watch a tmux-hosted worker and STOP the moment it needs the coordinator's
# attention. Reads the session JSONL (ground truth) plus the pane, and reports
# exactly one terminal state:
#   BLOCKED  — the agent called AskUserQuestion and is waiting for an answer
#              (the #31 drift stall: a worker sat on a question for minutes)
#   VERDICT  — (reviewer) a `VERDICT:` comment landed on the given PR
#   IDLE     — the transcript stopped growing and no turn is running (done/stalled)
#   DEAD     — the pane is gone
#   TIMEOUT  — hit the hard cycle cap with no stop condition
#
# BOUNDED BY CONSTRUCTION: a `seq 1 MAX` loop that always exits — never infinite.
#
# Usage: scripts/agent-watch.sh <role> [pr-number]
#   env: MAX=120 PERIOD=90 IDLE_MAX=4
set -euo pipefail
REPO="${ASKRAG_REPO:-/Users/nabin/projects/rags}"
role="${1:?usage: agent-watch.sh <role> [pr-number]}"
pr="${2:-}"
MAX="${MAX:-120}"; PERIOD="${PERIOD:-90}"; IDLE_MAX="${IDLE_MAX:-4}"

pane="$(cat "$REPO/.claude/run/$role.pane" 2>/dev/null || true)"
id="$(cat "$REPO/.claude/run/$role.session" 2>/dev/null || true)"
JF="$(find "$HOME/.claude/projects" -maxdepth 2 -name "$id.jsonl" 2>/dev/null | head -1)"

jl_lines() { { [ -n "$JF" ] && [ -f "$JF" ] && wc -l < "$JF"; } 2>/dev/null | tr -d ' ' || echo 0; }
# Blocked iff the LAST transcript entry is an assistant turn holding an
# unanswered AskUserQuestion tool_use (nothing follows it until the human picks).
last_is_question() {
  [ -n "$JF" ] && [ -f "$JF" ] || return 1
  tail -1 "$JF" | jq -e '
    select(.type=="assistant") | .message.content[]?
    | select(.type=="tool_use" and .name=="AskUserQuestion")' >/dev/null 2>&1
}
verdict_posted() {
  [ -n "$pr" ] || return 1
  local n
  n="$(gh pr view "$pr" --json comments \
        -q '[.comments[].body]|map(select(test("VERDICT:")))|length' 2>/dev/null || echo 0)"
  [ "${n:-0}" -gt 0 ]
}
_working() { [ -n "$pane" ] && tmux capture-pane -p -t "$pane" 2>/dev/null | grep -qi 'esc to interrupt'; }

prev="$(jl_lines)"; idle=0
for i in $(seq 1 "$MAX"); do
  sleep "$PERIOD"
  if [ -n "$pane" ] && ! tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$pane"; then
    echo "STOP[$role] DEAD: pane $pane gone at cycle $i"; exit 0
  fi
  if last_is_question; then
    echo "STOP[$role] BLOCKED: waiting on an AskUserQuestion at cycle $i — answer it in the pane"; exit 0
  fi
  if verdict_posted; then
    echo "STOP[$role] VERDICT: a VERDICT comment landed on PR #$pr at cycle $i"; exit 0
  fi
  cur="$(jl_lines)"
  if [ "$cur" -gt "$prev" ] || _working; then idle=0; else idle=$((idle+1)); fi
  prev="$cur"
  echo "[$role] cycle $i/$MAX: jsonl-lines=$cur idle-streak=$idle"
  if [ "$idle" -ge "$IDLE_MAX" ]; then
    echo "STOP[$role] IDLE: transcript quiet ${IDLE_MAX}x with no turn running at cycle $i (finished or stalled)"; exit 0
  fi
done
echo "STOP[$role] TIMEOUT: reached MAX=$MAX cycles with no stop condition"; exit 0
