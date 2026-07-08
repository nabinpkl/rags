"""Tests for askrag.cli's pure logic — no stdin/stdout wired up, no API call
(house rule): `_cited_ids` regex extraction, `_verify_citations` against a
tmp_path corpus, `ReplSession.ask`'s multi-turn message threading + running
cost accumulation (reusing test_loop.py's `ScriptedModelClient` fake), and
`_interactive`'s quit/EOF termination via a scripted input iterator."""

import pytest

from askrag import cli
from askrag.ingest.build_indexes import PaperRow, _write_corpus_db
from askrag.tools import registry
from tests.test_loop import (
    ScriptedModelClient,
    StubResult,
    make_settings,
    text_response,
    tool_use_response,
)

# --- _cited_ids ---------------------------------------------------------


def test_cited_ids_extracts_new_style_ids_including_versioned():
    text = (
        "Compare 2401.00001 (baseline) with 2401.00002v3 (follow-up); "
        "neither 12345 nor 999.99999 nor a plain 3.14159 is a real id."
    )
    assert cli._cited_ids(text) == {"2401.00001", "2401.00002"}


def test_cited_ids_empty_when_no_ids_present():
    assert cli._cited_ids("No citations in this answer at all.") == set()


# --- _verify_citations ---------------------------------------------------


def _paper(arxiv_id: str) -> PaperRow:
    return PaperRow(
        arxiv_id=arxiv_id,
        title="t",
        authors="a",
        abstract="x",
        categories="cs.CL",
        published="2024-01-01",
        version="v1",
        license=None,
        venue=None,
        authority=None,
        niche_idf=None,
        author_novelty=None,
        revisions=None,
        venue_rigor=None,
    )


def test_verify_citations_flags_missing_and_confirms_present(tmp_path, capsys):
    settings = make_settings(tmp_path, corpus_dir=tmp_path)
    _write_corpus_db(settings.corpus_db_path, [_paper("2401.00001")], [])

    cli._verify_citations(
        "See 2401.00001 for the real paper and 2401.99999 for one that doesn't exist.",
        settings=settings,
    )

    err = capsys.readouterr().err
    assert "2401.00001: verified" in err
    assert "2401.99999: NOT FOUND IN CORPUS.DB" in err


def test_verify_citations_no_op_when_no_ids_cited(tmp_path, capsys):
    # No corpus.db written at all — if this touched the DB it would raise
    # (connect_corpus opens mode=ro against a nonexistent file), so a clean
    # no-op here proves the early return, not a lucky pass.
    settings = make_settings(tmp_path, corpus_dir=tmp_path)
    cli._verify_citations("An answer that cites nothing.", settings=settings)
    assert capsys.readouterr().err == ""


# --- ReplSession.ask: message threading + running cost -------------------


def test_repl_session_ask_threads_messages_and_sums_cost_across_turns(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "dispatch", lambda name, args: StubResult({"n_papers": 6460}))
    settings = make_settings(tmp_path)
    client = ScriptedModelClient(
        [
            tool_use_response("t1", args={"op": "corpus_stats"}, tokens=(100, 10)),
            text_response("There are many papers.", tokens=(50, 10)),
            text_response("Nothing further to add.", tokens=(40, 5)),
        ]
    )
    session = cli.ReplSession(client=client, settings=settings, session_id="s1")

    result1 = session.ask("how many papers?")
    assert session.messages == result1.messages
    assert session.total_cost_usd == pytest.approx(result1.cost_usd)
    # The first turn's own user message is the first entry in its history.
    assert result1.messages[0] == {"role": "user", "content": "how many papers?"}

    result2 = session.ask("anything else?")
    assert session.messages == result2.messages
    assert session.total_cost_usd == pytest.approx(result1.cost_usd + result2.cost_usd)
    # Threading holds: turn 2's history still carries turn 1's own first
    # entry — a dropped `self.messages = result.messages` would instead
    # start turn 2 from an empty history, making this the "anything else?"
    # entry instead.
    assert result2.messages[0] == {"role": "user", "content": "how many papers?"}
    assert len(result2.messages) > len(result1.messages)


# --- _interactive: quit/EOF termination -----------------------------------


class _UncalledClient:
    """Satisfies the `ModelClient` protocol without ever being invoked — the
    tests below replace `ReplSession.ask` itself, so `.create()` firing
    would mean the replacement didn't take."""

    def create(self, *, system, messages, tools):
        raise AssertionError("the model client should never be called here")


def _recording_session(tmp_path) -> tuple[cli.ReplSession, list[str]]:
    # A real ReplSession with `.ask` swapped for a recorder — `_interactive`
    # only ever calls `.ask`, and this keeps the ty-checked `ReplSession`
    # parameter type honest instead of hand-rolling a duck-typed stand-in.
    session = cli.ReplSession(client=_UncalledClient(), settings=make_settings(tmp_path))
    asked: list[str] = []
    session.ask = asked.append  # ty: ignore[invalid-assignment]
    return session, asked


def test_interactive_terminates_on_quit(tmp_path, monkeypatch):
    inputs = iter(["first question", "quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session, asked = _recording_session(tmp_path)

    cli._interactive(session)

    assert asked == ["first question"]


def test_interactive_terminates_on_eof(tmp_path, monkeypatch):
    inputs = iter(["only question"])

    def fake_input(prompt=""):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)
    session, asked = _recording_session(tmp_path)

    cli._interactive(session)

    assert asked == ["only question"]


def test_interactive_skips_blank_input_without_asking(tmp_path, monkeypatch):
    inputs = iter(["", "  ", "quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    session, asked = _recording_session(tmp_path)

    cli._interactive(session)

    assert asked == []
