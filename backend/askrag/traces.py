"""traces.db — the durable per-run PRODUCT record (D13): every agent run's tool
calls, tokens, cost, latency, session, hashed IP, and showcase flag.

Distinct from askrag/telemetry.py (D15/#43): telemetry is OPS signal (OTel
spans/logs, ephemeral, greppable); traces.db is the product record that
budgets (#21), the admin dashboard, the timeline UI, evals (D14), and replay
(D11) read back. A showcase replay is just a recorded trace flagged
``showcase=1`` — no separate store or format (§4c decision 3).

Append-only: rows are written once by ``record_run`` and never mutated. WAL
(set by db.connect_traces) lets many processes write concurrently; readers
never block writers. Aggregations (spend per day / session / IP) are plain SQL
over indexed columns — the SQL is portfolio material, so no ORM (D13/§4b).

Privacy (§6 posture): the raw client IP is NEVER persisted. ``record_run``
hashes it with a config salt before it touches the DB; only ``ip_hash`` is
stored, so the per-IP budget layer (D11) works without holding a raw address.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from askrag import db
from askrag.config import Settings, get_settings

# CREATE TABLE IF NOT EXISTS does not migrate an existing traces.db: adding a
# column here (as #30 did with question/answer_text) is a no-op against a
# table that already exists, and the next INSERT fails with "table runs has
# no column named ...". Any column change to this schema needs the dev
# traces.db deleted so it regenerates. (decisions.md 2026-07-05 covers this;
# this is the durable home a future schema-editor actually reads.)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,   -- UTC ISO 8601
    day         TEXT NOT NULL,   -- UTC date (YYYY-MM-DD); the spend_today key
    session_id  TEXT NOT NULL,
    ip_hash     TEXT NOT NULL,   -- salted SHA-256; raw IP is never stored (§6)
    question    TEXT NOT NULL,   -- the user message this run answered
    answer_text TEXT NOT NULL,   -- the turn's final answer, our own AI-generated
                                  -- summary (§6c) — lets a showcase replay (D11)
                                  -- reproduce the answer, not just the timeline
    tokens_in   INTEGER NOT NULL,
    tokens_out  INTEGER NOT NULL,
    cost_usd    REAL NOT NULL,
    latency_ms  REAL NOT NULL,
    tool_calls  TEXT NOT NULL,   -- JSON array of per-call records
    showcase    INTEGER NOT NULL -- 0/1; a replayable showcase trace (D11)
);
CREATE INDEX IF NOT EXISTS idx_runs_day ON runs (day);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs (session_id);
CREATE INDEX IF NOT EXISTS idx_runs_ip_day ON runs (ip_hash, day);
CREATE INDEX IF NOT EXISTS idx_runs_showcase ON runs (showcase);
"""


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call within an agent run — name, the args it was invoked
    with, and its outcome. Loop-owned shape (askrag/agent/loop.py constructs
    these on every dispatch); traces.py just persists/reads them back (D13).
    Replaces the bare `dict[str, Any]` this field used before #23 defined the
    real per-call shape (carry-forward review note, #20/#23)."""

    name: str
    args: dict[str, Any]
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class Run:
    """One persisted agent run; the shape budgets/admin/replay read back."""

    run_id: str
    created_at: str
    day: str
    session_id: str
    ip_hash: str
    question: str
    answer_text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    tool_calls: tuple[ToolCallRecord, ...]
    showcase: bool


def _settings(settings: Settings | None) -> Settings:
    return settings if settings is not None else get_settings()


def _connect(settings: Settings):
    conn = db.connect_traces(settings.traces_db_path)
    conn.executescript(_SCHEMA)
    return conn


def hash_ip(ip: str, *, settings: Settings | None = None) -> str:
    """Salted SHA-256 of a client IP — the only IP form that reaches the DB.

    Deterministic (same ip+salt → same digest) so the per-IP budget layer can
    aggregate, but not reversible to the raw address without the salt.
    """
    salt = _settings(settings).trace_ip_hash_salt.get_secret_value()
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


def record_run(
    *,
    session_id: str,
    ip: str,
    question: str,
    answer_text: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: float,
    tool_calls: list[ToolCallRecord],
    showcase: bool,
    created_at: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Append one run; returns its run_id. The raw ``ip`` is hashed here and
    never stored. ``created_at`` defaults to now (UTC); pass it only for
    backfills/tests."""
    settings = _settings(settings)
    run_id = uuid.uuid4().hex
    when = created_at if created_at is not None else datetime.now(UTC).isoformat()
    day = when[:10]  # ISO date prefix; both now() and passed values are UTC ISO
    conn = _connect(settings)
    try:
        with conn:  # transaction: commit on success, rollback on error
            conn.execute(
                "INSERT INTO runs (run_id, created_at, day, session_id, ip_hash, "
                "question, answer_text, tokens_in, tokens_out, cost_usd, latency_ms, "
                "tool_calls, showcase) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    when,
                    day,
                    session_id,
                    hash_ip(ip, settings=settings),
                    question,
                    answer_text,
                    tokens_in,
                    tokens_out,
                    cost_usd,
                    latency_ms,
                    json.dumps([asdict(t) for t in tool_calls], ensure_ascii=False),
                    int(showcase),
                ),
            )
    finally:
        conn.close()
    return run_id


def _scalar_spend(sql: str, params: tuple[Any, ...], settings: Settings) -> float:
    conn = _connect(settings)
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    # SUM over no rows is NULL; report it as 0.0 spend.
    return float(row[0]) if row[0] is not None else 0.0


def spend_today(*, settings: Settings | None = None) -> float:
    """Total USD spent across all runs stamped with today's UTC date (D11)."""
    settings = _settings(settings)
    today = datetime.now(UTC).date().isoformat()
    return _scalar_spend("SELECT SUM(cost_usd) FROM runs WHERE day = ?", (today,), settings)


def spend_for_session(session_id: str, *, settings: Settings | None = None) -> float:
    """Total USD spent by one session across all days (per-session cap, D11)."""
    return _scalar_spend(
        "SELECT SUM(cost_usd) FROM runs WHERE session_id = ?",
        (session_id,),
        _settings(settings),
    )


def spend_for_ip_today(ip_hash: str, *, settings: Settings | None = None) -> float:
    """Total USD spent today by one hashed IP (per-IP daily cap, D11). Takes the
    hash, not the raw IP — callers hash via ``hash_ip`` first."""
    settings = _settings(settings)
    today = datetime.now(UTC).date().isoformat()
    return _scalar_spend(
        "SELECT SUM(cost_usd) FROM runs WHERE ip_hash = ? AND day = ?",
        (ip_hash, today),
        settings,
    )


def message_count_for_session(session_id: str, *, settings: Settings | None = None) -> int:
    """How many runs (one per user message turn) this session has recorded —
    the per-session message cap's state (D11: session budget is a message count)."""
    conn = _connect(_settings(settings))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE session_id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    return int(row[0])


def _row_to_run(row) -> Run:
    return Run(
        run_id=row["run_id"],
        created_at=row["created_at"],
        day=row["day"],
        session_id=row["session_id"],
        ip_hash=row["ip_hash"],
        question=row["question"],
        answer_text=row["answer_text"],
        tokens_in=row["tokens_in"],
        tokens_out=row["tokens_out"],
        cost_usd=row["cost_usd"],
        latency_ms=row["latency_ms"],
        tool_calls=tuple(
            ToolCallRecord(name=t["name"], args=t["args"], ok=t["ok"], error=t.get("error"))
            for t in json.loads(row["tool_calls"])
        ),
        showcase=bool(row["showcase"]),
    )


def get_run(run_id: str, *, settings: Settings | None = None) -> Run | None:
    conn = _connect(_settings(settings))
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    return _row_to_run(row) if row is not None else None


def get_showcase_traces(*, settings: Settings | None = None) -> list[Run]:
    """Every showcase-flagged run, oldest first — the replay pool (D11)."""
    conn = _connect(_settings(settings))
    try:
        rows = conn.execute("SELECT * FROM runs WHERE showcase = 1 ORDER BY created_at").fetchall()
    finally:
        conn.close()
    return [_row_to_run(row) for row in rows]
