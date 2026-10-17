"""Tests for askrag.sources.claude_transcripts.read_sessions (synthetic logs)."""

import json

from askrag.sources.claude_transcripts.read_sessions import (
    clean_prompt,
    read_session_file,
    read_sessions,
    tool_line,
    tool_names,
)

SID = "11111111-2222-3333-4444-555555555555"


def rec(kind, content=None, **extra):
    r = {"type": kind, "sessionId": SID, "timestamp": "2026-10-05T09:00:00Z", "cwd": "/w/rags"}
    if content is not None:
        r["message"] = {"role": kind, "content": content}
    r.update(extra)
    return r


def write(path, records, tail=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + tail)
    return path


def test_a_turn_is_a_prompt_plus_replies_and_tool_lines(tmp_path):
    path = write(
        tmp_path / "proj" / f"{SID}.jsonl",
        [
            rec("ai-title", aiTitle="Fix the map"),
            rec("user", "why is the map blank <system-reminder>hidden</system-reminder>"),
            rec(
                "assistant",
                [
                    {"type": "thinking", "thinking": "private reasoning"},
                    {"type": "text", "text": "Checking the cache headers."},
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "curl -sI /paper-map/map.json", "description": "Head"},
                    },
                ],
            ),
            rec("user", [{"type": "tool_result", "content": "HTTP/1.1 404 secret output"}]),
            rec("assistant", [{"type": "text", "text": "Caddy 404s it."}]),
            rec("user", "fix it", isMeta=True),
            rec("user", "fix it"),
            rec("user", "sub", isSidechain=True),
        ],
        tail='{"type": "user", "trunc',
    )
    [session] = read_session_file(path, tool_input_chars=200)
    assert (session.session_id, session.project, session.day, session.title) == (
        SID,
        "rags",
        20261005,
        "Fix the map",
    )
    assert [t.index for t in session.turns] == [1, 2]
    first = session.turns[0]
    assert first.prompt == "why is the map blank"
    assert first.text == (
        "User: why is the map blank\n"
        "Claude: Checking the cache headers.\n"
        "[Bash] Head | curl -sI /paper-map/map.json\n"
        "Claude: Caddy 404s it."
    )
    assert "secret output" not in first.text and "private reasoning" not in first.text


def test_a_custom_title_beats_the_ai_title_and_untitled_falls_back(tmp_path):
    path = write(
        tmp_path / "p" / "a.jsonl",
        [rec("custom-title", customTitle="Mine"), rec("ai-title", aiTitle="AI"), rec("user", "hi")],
    )
    assert read_session_file(path, 200)[0].title == "Mine"
    plain = write(tmp_path / "p" / "b.jsonl", [rec("user", "deploy the tunnel please")])
    assert read_session_file(plain, 200)[0].title == "deploy the tunnel please"


def test_long_tool_input_is_cut_and_tags_are_stripped():
    line = tool_line("Read", {"file_path": "/x/" + "a" * 300}, max_chars=40)
    assert line.startswith("[Read] /x/aaa") and line.endswith("...") and len(line) == 47
    assert clean_prompt("<command-name>/compact</command-name>  now") == "/compact now"


def test_sessions_are_read_across_projects_in_id_order(tmp_path):
    write(tmp_path / "b" / "x.jsonl", [rec("user", "two", sessionId="b-session")])
    write(tmp_path / "a" / "y.jsonl", [rec("user", "one", sessionId="a-session")])
    write(tmp_path / "a" / "empty.jsonl", [rec("ai-title", aiTitle="no turns")])
    assert [s.session_id for s in read_sessions(tmp_path, 200)] == ["a-session", "b-session"]


def test_tool_names_are_read_back_from_tool_lines_only():
    text = "User: ask the [owner]\n[Bash] run | uv sync\n[AskUserQuestion] pick one"
    assert tool_names(text) == {"Bash", "AskUserQuestion"}
