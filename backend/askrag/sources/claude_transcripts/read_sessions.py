"""Claude Code session logs -> sessions of turns (D21).

A session log is one jsonl per session under `<root>/<project-folder>/`. A
turn is one prompt the person typed and everything the assistant did until
the next one: its prose replies and one line per tool call (the tool's name
and the head of its input). Indexed text is what was SAID and DONE, never
what a tool returned: tool output is file dumps, command logs and secrets,
and it is not what anyone remembers a session by.

Skipped: subagent records (`isSidechain`), harness-injected records
(`isMeta`), compaction summaries (they restate earlier turns), thinking
blocks, and `<system-reminder>` and local-command blocks inside prompts.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger("askrag.sources.claude_transcripts.read_sessions")

# Harness text inside a prompt that the person did not type.
_DROP_BLOCKS = re.compile(
    r"<(system-reminder|local-command-stdout|local-command-stderr|local-command-caveat)>"
    r".*?</\1>",
    re.S,
)
_TAG = re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^<>]*)?>")
# The input fields that say what a tool call did, in the order they are tried.
_TOOL_PREFIX = re.compile(r"(?m)^\[([^\]\s]+)\]")
_TOOL_FIELDS = ("description", "command", "file_path", "path", "pattern", "query", "url", "prompt")


@dataclass
class Turn:
    index: int  # 1-based position in the session
    prompt: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join([f"User: {self.prompt}", *self.lines])


@dataclass
class Session:
    session_id: str
    project: str
    day: int  # YYYYMMDD of the first record
    title: str
    turns: list[Turn]


def clean_prompt(text: str) -> str:
    text = _DROP_BLOCKS.sub(" ", text)
    text = _TAG.sub(" ", text)
    return " ".join(text.split())


def tool_line(name: str, tool_input: Any, max_chars: int) -> str:
    """`[Bash] Run the tests | uv run pytest -q`, cut to max_chars of input."""
    parts: list[str] = []
    if isinstance(tool_input, dict):
        for key in _TOOL_FIELDS:
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(" ".join(value.split()))
            if len(parts) == 2:
                break
    summary = " | ".join(parts)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3] + "..."
    return f"[{name}] {summary}".rstrip()


def tool_names(text: str) -> set[str]:
    """The tool names `tool_line` wrote into a turn's text."""
    return set(_TOOL_PREFIX.findall(text))


def _prompt_of(content: Any) -> str | None:
    """The typed prompt of a user record, or None for tool results."""
    if isinstance(content, str):
        return clean_prompt(content)
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        texts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return clean_prompt(" ".join(texts))
    return None


def _project_of(cwd: str | None, folder: str) -> str:
    return Path(cwd).name if cwd else folder


def read_session_file(path: Path, tool_input_chars: int) -> list[Session]:
    """Every session in one log file (normally exactly one)."""
    sessions: dict[str, Session] = {}
    titles: dict[str, tuple[int, str]] = {}  # session -> (priority, title)
    bad_lines = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            # A log being written mid-line; counted, never silently fixed.
            bad_lines += 1
            continue
        kind = record.get("type")
        sid = record.get("sessionId")
        if not sid:
            continue
        if kind in ("custom-title", "ai-title"):
            title = record.get("customTitle") or record.get("aiTitle") or ""
            priority = 2 if kind == "custom-title" else 1
            if title and priority >= titles.get(sid, (0, ""))[0]:
                titles[sid] = (priority, " ".join(title.split()))
            continue
        if kind not in ("user", "assistant"):
            continue
        if record.get("isSidechain") or record.get("isMeta") or record.get("isCompactSummary"):
            continue
        session = sessions.get(sid)
        if session is None:
            stamp = str(record.get("timestamp", ""))
            day = int(stamp[:10].replace("-", "")) if len(stamp) >= 10 else 0
            session = Session(sid, _project_of(record.get("cwd"), path.parent.name), day, "", [])
            sessions[sid] = session
        content = (record.get("message") or {}).get("content")
        if kind == "user":
            prompt = _prompt_of(content)
            if prompt:
                session.turns.append(Turn(len(session.turns) + 1, prompt))
            continue
        if not session.turns or not isinstance(content, list):
            continue  # assistant output before any prompt: nothing to hang it on
        turn = session.turns[-1]
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                turn.lines.append(f"Claude: {' '.join(block['text'].split())}")
            elif block.get("type") == "tool_use":
                turn.lines.append(
                    tool_line(str(block.get("name", "tool")), block.get("input"), tool_input_chars)
                )
    if bad_lines:
        _log.warning(f"{path.name}: {bad_lines} unparseable line(s) skipped")
    for sid, session in sessions.items():
        first = session.turns[0].prompt if session.turns else ""
        session.title = titles.get(sid, (0, first[:80]))[1] or "untitled session"
    return [s for s in sessions.values() if s.turns]


def read_sessions(root: Path, tool_input_chars: int) -> list[Session]:
    """All sessions under root, sorted by id so a rebuild is deterministic."""
    found: dict[str, Session] = {}
    for path in sorted(root.glob("*/*.jsonl")):
        for session in read_session_file(path, tool_input_chars):
            if session.session_id in found:
                # A resumed session can span files; keep turns in file order.
                kept = found[session.session_id]
                for turn in session.turns:
                    kept.turns.append(Turn(len(kept.turns) + 1, turn.prompt, turn.lines))
            else:
                found[session.session_id] = session
    return [found[k] for k in sorted(found)]
