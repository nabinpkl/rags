"""Tests for askrag.traces — the durable product record (D13), distinct from
OTel ops telemetry (#43). Security-relevant behavior is test-first (§6 posture):
raw IPs are NEVER persisted; only salted hashes. Concurrency and spend
aggregation are exercised for real, not asserted by pragma alone."""

import concurrent.futures as cf
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from askrag import traces
from askrag.config import Settings


def make_settings(tmp_path, **overrides):
    # _env_file=None isolates from a developer's local .env without a cwd change
    # (the concurrency test's subprocess writers need it too, where a chdir
    # fixture would not apply). ty lacks the pydantic-settings init stub.
    return Settings(traces_db_path=tmp_path / "traces.db", _env_file=None, **overrides)  # ty: ignore[unknown-argument]


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


def sample_run(**overrides):
    base = dict(
        session_id="sess-1",
        ip="203.0.113.7",
        question="what is chain of thought?",
        answer_text="Chain of thought is a prompting technique.",
        tokens_in=1000,
        tokens_out=200,
        cost_usd=0.012,
        latency_ms=850.0,
        tool_calls=[traces.ToolCallRecord(name="search_corpus", args={"query": "x"}, ok=True)],
        showcase=False,
    )
    base.update(overrides)
    return base


# --- security: IP is hashed, never stored raw (test-first, §6) --------------


def test_record_run_never_persists_raw_ip(settings):
    raw_ip = "198.51.100.42"
    traces.record_run(**sample_run(ip=raw_ip), settings=settings)
    # Scan the entire DB file: the raw IP must appear nowhere on disk.
    blob = Path(settings.traces_db_path).read_bytes()
    assert raw_ip.encode() not in blob


def test_ip_hash_is_stable_and_salted(settings):
    salted = make_settings(Path(settings.traces_db_path).parent, trace_ip_hash_salt="pepper")
    a = traces.hash_ip("198.51.100.42", settings=settings)
    b = traces.hash_ip("198.51.100.42", settings=settings)
    c = traces.hash_ip("198.51.100.42", settings=salted)
    assert a == b  # deterministic
    assert a != "198.51.100.42"  # not the raw value
    assert a != c  # salt changes the digest
    assert len(a) == 64  # sha-256 hex


def test_distinct_ips_hash_distinctly(settings):
    assert traces.hash_ip("10.0.0.1", settings=settings) != traces.hash_ip(
        "10.0.0.2", settings=settings
    )


# --- spend aggregation: per-day and per-session (real assertions) -----------


def test_spend_today_sums_only_todays_runs(settings):
    traces.record_run(**sample_run(cost_usd=0.10), settings=settings)
    traces.record_run(**sample_run(cost_usd=0.05), settings=settings)
    # A run stamped yesterday must not count toward today's spend.
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    traces.record_run(**sample_run(cost_usd=999.0), created_at=yesterday, settings=settings)
    assert traces.spend_today(settings=settings) == pytest.approx(0.15)


def test_spend_for_session_sums_that_session_only(settings):
    traces.record_run(**sample_run(session_id="a", cost_usd=0.02), settings=settings)
    traces.record_run(**sample_run(session_id="a", cost_usd=0.03), settings=settings)
    traces.record_run(**sample_run(session_id="b", cost_usd=1.00), settings=settings)
    assert traces.spend_for_session("a", settings=settings) == pytest.approx(0.05)
    assert traces.spend_for_session("b", settings=settings) == pytest.approx(1.00)


def test_message_count_for_session_counts_runs(settings):
    assert traces.message_count_for_session("s", settings=settings) == 0
    traces.record_run(**sample_run(session_id="s"), settings=settings)
    traces.record_run(**sample_run(session_id="s"), settings=settings)
    traces.record_run(**sample_run(session_id="other"), settings=settings)
    assert traces.message_count_for_session("s", settings=settings) == 2


def test_spend_for_ip_today_sums_that_ip_only(settings):
    traces.record_run(**sample_run(ip="1.1.1.1", cost_usd=0.04), settings=settings)
    traces.record_run(**sample_run(ip="1.1.1.1", cost_usd=0.04), settings=settings)
    traces.record_run(**sample_run(ip="2.2.2.2", cost_usd=0.09), settings=settings)
    ip_hash = traces.hash_ip("1.1.1.1", settings=settings)
    assert traces.spend_for_ip_today(ip_hash, settings=settings) == pytest.approx(0.08)


def test_spend_today_zero_on_empty_db(settings):
    assert traces.spend_today(settings=settings) == 0.0


# --- showcase / replay fetch ------------------------------------------------


def test_get_showcase_traces_returns_only_flagged(settings):
    traces.record_run(**sample_run(session_id="live", showcase=False), settings=settings)
    rid = traces.record_run(**sample_run(session_id="demo", showcase=True), settings=settings)
    shown = traces.get_showcase_traces(settings=settings)
    assert [t.run_id for t in shown] == [rid]
    assert shown[0].showcase is True
    assert shown[0].session_id == "demo"


def test_recorded_run_roundtrips_fields(settings):
    call = traces.ToolCallRecord(name="read_paper", args={"paper_id": "2401.00001"}, ok=True)
    rid = traces.record_run(**sample_run(tool_calls=[call]), settings=settings)
    run = traces.get_run(rid, settings=settings)
    assert run is not None
    assert run.run_id == rid
    assert run.question == "what is chain of thought?"
    assert run.answer_text == "Chain of thought is a prompting technique."
    assert run.tokens_in == 1000
    assert run.tokens_out == 200
    assert run.cost_usd == pytest.approx(0.012)
    assert run.latency_ms == pytest.approx(850.0)
    assert run.tool_calls == (call,)


def test_recorded_run_roundtrips_tool_call_error(settings):
    call = traces.ToolCallRecord(
        name="read_paper", args={"paper_id": "bogus"}, ok=False, error="no such paper"
    )
    rid = traces.record_run(**sample_run(tool_calls=[call]), settings=settings)
    run = traces.get_run(rid, settings=settings)
    assert run is not None
    assert run.tool_calls == (call,)


def test_recorded_run_roundtrips_tool_call_citations(settings):
    call = traces.ToolCallRecord(
        name="search_corpus",
        args={"query": "cot"},
        ok=True,
        citations=(
            traces.Citation(paper_id="2401.00001", chunk_id="2401.00001#0"),
            traces.Citation(paper_id="2401.00001", chunk_id="2401.00001#1"),
        ),
    )
    rid = traces.record_run(**sample_run(tool_calls=[call]), settings=settings)
    run = traces.get_run(rid, settings=settings)
    assert run is not None
    assert run.tool_calls == (call,)


def test_tool_call_citations_default_to_empty_when_absent_from_stored_json(settings, tmp_path):
    # Simulates a pre-#27 traces.db row: tool_calls JSON has no "citations"
    # key at all. Reading it back must not KeyError (DECISIONS.md, issue #27).
    conn = sqlite3.connect(tmp_path / "traces.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, created_at TEXT, day TEXT,"
        " session_id TEXT, ip_hash TEXT, question TEXT, answer_text TEXT, tokens_in INTEGER,"
        " tokens_out INTEGER, cost_usd REAL, latency_ms REAL, tool_calls TEXT, showcase INTEGER)"
    )
    conn.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "old1",
            "2026-07-01T00:00:00+00:00",
            "2026-07-01",
            "s",
            "h",
            "q",
            "a",
            1,
            1,
            0.0,
            1.0,
            '[{"name": "search_corpus", "args": {}, "ok": true, "error": null}]',
            0,
        ),
    )
    conn.commit()
    conn.close()
    run = traces.get_run("old1", settings=settings)
    assert run is not None
    assert run.tool_calls == (
        traces.ToolCallRecord(name="search_corpus", args={}, ok=True, error=None),
    )


# --- concurrency: WAL actually allows concurrent writers --------------------


def _writer(db_path: str, session_id: str, n: int) -> tuple[int, int]:
    # Runs in a separate process (real .py module import path, not python -c);
    # the process pool re-imports this module, so the top-level askrag imports
    # are available in the worker.
    # Returns (rows_written, locked_errors): a missing busy_timeout surfaces as
    # "database is locked" under this contention, so we count those explicitly.
    s = Settings(traces_db_path=Path(db_path), _env_file=None)  # ty: ignore[unknown-argument]
    written = locked = 0
    for i in range(n):
        try:
            traces.record_run(
                session_id=session_id,
                ip=f"10.0.0.{i % 5}",
                question="q",
                answer_text="a",
                tokens_in=1,
                tokens_out=1,
                cost_usd=0.001,
                latency_ms=1.0,
                tool_calls=[],
                showcase=False,
                settings=s,
            )
            written += 1
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc):
                raise
            locked += 1
    return written, locked


def test_concurrent_writers_do_not_lose_or_corrupt_rows(settings):
    # Initialize the schema once before fanning out (avoids a create race that
    # would mask the real question: can WAL + busy_timeout take concurrent
    # inserts without losing rows or throwing "database is locked"?).
    traces.record_run(**sample_run(), settings=settings)
    db_path = str(settings.traces_db_path)
    writers, per_writer = 8, 50
    with cf.ProcessPoolExecutor(max_workers=writers) as pool:
        futures = [pool.submit(_writer, db_path, f"w{w}", per_writer) for w in range(writers)]
        results = [f.result(timeout=120) for f in futures]
    written = sum(w for w, _ in results)
    locked = sum(loc for _, loc in results)
    assert locked == 0, f"{locked} writes hit 'database is locked' (busy_timeout missing?)"
    assert written == writers * per_writer
    # Every row is present and the DB is not corrupt.
    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    assert integrity == "ok"
    assert total == 1 + writers * per_writer  # the seed row + all concurrent rows
