#!/usr/bin/env bash
# Live action feed for a tmux-hosted worker agent (implementor/reviewer/auditor).
# Prints one line per tool call, flagging mutating tools, from the live-appended
# session jsonl. Human peek surface: read-only, never drives the agent.
#
# The jsonl is located by uuid across all project dirs (a worker runs in a git
# worktree, so its project-dir hash differs from the primary repo's).
#
# Usage: scripts/agent-feed.sh <role|session-uuid>
set -euo pipefail

REPO="${ASKRAG_REPO:-/Users/nabin/projects/rags}"
arg="${1:?usage: agent-feed.sh <role|session-uuid>}"

# Resolve a role name to its recorded uuid; accept a raw uuid directly.
if [[ "$arg" =~ ^[0-9a-f]{8}- ]]; then
  id="$arg"
elif [ -f "$REPO/.claude/run/$arg.session" ]; then
  id="$(cat "$REPO/.claude/run/$arg.session")"
else
  echo "no run-file for role '$arg' and it is not a uuid" >&2; exit 1
fi

# Find the jsonl by uuid anywhere under ~/.claude/projects (worktree-agnostic).
f=""
for _ in $(seq 1 30); do
  f="$(find "$HOME/.claude/projects" -maxdepth 2 -name "$id.jsonl" 2>/dev/null | head -1)"
  [ -n "$f" ] && break
  sleep 0.5
done
[ -n "$f" ] || { echo "no session jsonl for $id under ~/.claude/projects yet" >&2; exit 1; }

echo "feed: $f (Ctrl-C to stop watching; the agent keeps running)" >&2
tail -n +1 -f "$f" | jq -rc --unbuffered '
  .message.content[]? | select(.type == "tool_use") as $t
  | ( $t.input.command // $t.input.file_path // $t.input.description
      // ($t.input | keys | join(",")) ) as $d
  | ( if ($t.name | test("^(Bash|Edit|Write|NotebookEdit)$"))
      then "MUTATE  " else "        " end )
    + $t.name + "  " + ($d | tostring | gsub("\\s+"; " ") | .[0:180])
' 2>/dev/null
