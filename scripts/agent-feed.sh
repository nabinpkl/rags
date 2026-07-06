#!/usr/bin/env bash
# Live action feed for a tmux-hosted worker agent (implementor / reviewer).
#
# Tails the worker's Claude Code session jsonl and prints one line per tool
# call, flagging mutating tools (Bash/Edit/Write/NotebookEdit) so a human can
# random-sample the worker's actions and catch a wrong one mid-flight. This is
# the "peek" surface: read-only, it never drives or edits the agent.
#
# Usage: scripts/agent-feed.sh <session-uuid>
#   (the uuid is what agent-spawn.sh prints; the jsonl path is derived from it)
set -euo pipefail

PROJ="${CLAUDE_PROJECT_DIR:-$HOME/.claude/projects/-Users-nabin-projects-rags}"
REPO="${REPO:-/Users/nabin/projects/rags}"
arg="${1:?usage: agent-feed.sh <role|session-uuid>}"

# Accept either a raw uuid or a role name (resolved via the run-file that
# agent-spawn.sh wrote). A uuid contains a '-' and no path; a role is a plain word.
if [[ "$arg" =~ ^[0-9a-f]{8}- ]]; then
  id="$arg"
elif [ -f "$REPO/.claude/run/$arg.session" ]; then
  id="$(cat "$REPO/.claude/run/$arg.session")"
else
  echo "no run-file for role '$arg' at $REPO/.claude/run/$arg.session (and it is not a uuid)" >&2
  exit 1
fi
f="$PROJ/$id.jsonl"

# The worker may still be booting; wait up to 15s for its jsonl to appear.
for _ in $(seq 1 30); do [ -f "$f" ] && break; sleep 0.5; done
[ -f "$f" ] || { echo "no session jsonl at $f" >&2; exit 1; }

echo "feed: $f (Ctrl-C to stop watching; the agent keeps running)" >&2
# -n +1 replays the run so far, then streams. --unbuffered flushes each line as
# it lands (jq block-buffers to a pipe otherwise). Detail is squashed to one
# scannable line. A malformed/partial line is skipped.
tail -n +1 -f "$f" | jq -rc --unbuffered '
  .message.content[]? | select(.type == "tool_use") as $t
  | ( $t.input.command
      // $t.input.file_path
      // $t.input.description
      // ($t.input | keys | join(",")) ) as $d
  | ( if ($t.name | test("^(Bash|Edit|Write|NotebookEdit)$"))
      then "MUTATE  " else "        " end )
    + $t.name + "  " + ($d | tostring | gsub("\\s+"; " ") | .[0:180])
' 2>/dev/null
