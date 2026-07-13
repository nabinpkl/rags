"""Tests for askrag.agent.budgets — D11 layered cap cascade, enforced
server-side (security-relevant, so test-first). Every layer trips at its EXACT
boundary (at-limit passes, over-limit trips — off-by-one matters); the global
cap flips to REPLAY, not DENY; and no *sequence* of requests can push cumulative
spend past the global cap (the check-then-record loop, run sequentially)."""

import pytest

from askrag import traces
from askrag.agent import budgets
from askrag.agent.budgets import Verdict
from askrag.config import Settings

SESSION = "sess-1"
IP = "203.0.113.10"

# Caps small and exact so boundaries are unambiguous.
CAPS = dict(
    session_message_cap=3,
    ip_daily_spend_cap_usd=0.10,
    global_daily_spend_cap_usd=0.50,
)


def make_settings(tmp_path, **overrides):
    # ty can't verify **dict against the typed Settings signature; the values
    # are the small-cap fixtures above.
    kwargs = {**CAPS, **overrides}
    return Settings(traces_db_path=tmp_path / "traces.db", _env_file=None, **kwargs)  # ty: ignore[unknown-argument, invalid-argument-type]


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


def spend(settings, *, cost, session=SESSION, ip=IP):
    traces.record_run(
        session_id=session,
        ip=ip,
        question="q",
        answer_text="a",
        tokens_in=1,
        tokens_out=1,
        cost_usd=cost,
        latency_ms=1.0,
        tool_calls=[],
        showcase=False,
        settings=settings,
    )


# --- clean slate: allow -----------------------------------------------------


def test_empty_state_allows(settings):
    decision = budgets.check(SESSION, IP, settings=settings)
    assert decision.verdict is Verdict.ALLOW


# --- session message cap (a COUNT, D11) trips at its exact boundary ----------


def test_session_cap_allows_up_to_limit_then_denies(settings):
    # cap = 3 messages: after 2 recorded runs a 3rd is still allowed; after 3 it denies.
    spend(settings, cost=0.0)
    spend(settings, cost=0.0)
    assert budgets.check(SESSION, IP, settings=settings).verdict is Verdict.ALLOW
    spend(settings, cost=0.0)  # now 3 recorded == cap
    denied = budgets.check(SESSION, IP, settings=settings)
    assert denied.verdict is Verdict.DENY
    assert "session" in denied.reason.lower()


# --- per-IP daily spend cap trips at its exact boundary ----------------------


def test_ip_cap_allows_below_denies_at_limit(settings):
    # 0.05 + 0.05 == 0.10 exactly in float (0.09 + 0.01 would drift below the
    # cap and wrongly ALLOW — money sums use small round values by convention).
    spend(settings, cost=0.05)  # below 0.10 cap
    assert budgets.check(SESSION, IP, settings=settings).verdict is Verdict.ALLOW
    spend(settings, cost=0.05)  # cumulative 0.10 == cap
    denied = budgets.check(SESSION, IP, settings=settings)
    assert denied.verdict is Verdict.DENY
    # User-facing reason avoids jargon ("IP") — it names the limit in plain terms.
    assert "limit" in denied.reason.lower()


def test_ip_cap_is_per_ip(settings):
    spend(settings, cost=0.10, ip="1.1.1.1")  # this IP is at its cap
    # A different IP with a fresh session is unaffected.
    other = budgets.check("sess-2", "2.2.2.2", settings=settings)
    assert other.verdict is Verdict.ALLOW


# --- global daily cap trips into REPLAY (not DENY) at its exact boundary -----


def test_global_cap_flips_to_replay_at_limit(settings):
    # Spread across IPs so the per-IP cap never trips first.
    for i in range(5):
        spend(settings, cost=0.09, ip=f"10.0.0.{i}", session=f"s{i}")  # 0.45 total, below 0.50
    assert budgets.check("s-new", "10.0.0.99", settings=settings).verdict is Verdict.ALLOW
    spend(settings, cost=0.05, ip="10.0.0.5", session="s5")  # cumulative 0.50 == global cap
    replay = budgets.check("s-new", "10.0.0.99", settings=settings)
    assert replay.verdict is Verdict.REPLAY
    assert replay.reason  # user-displayable


def test_global_cap_takes_precedence_over_session_and_ip(settings):
    # Even a brand-new session/IP gets REPLAY once the global cap is spent —
    # the global backstop is checked and REPLAY wins over a would-be ALLOW.
    for i in range(10):
        spend(settings, cost=0.05, ip=f"172.16.0.{i}", session=f"g{i}")  # 0.50 total
    decision = budgets.check("fresh", "172.16.9.9", settings=settings)
    assert decision.verdict is Verdict.REPLAY


# --- reasons are user-displayable strings -----------------------------------


def test_all_reasons_are_nonempty_displayable_strings(settings):
    # deny (session)
    for _ in range(3):
        spend(settings, cost=0.0)
    d = budgets.check(SESSION, IP, settings=settings)
    assert isinstance(d.reason, str) and d.reason.strip()
    assert "\n" not in d.reason  # single-line, banner-friendly


def test_allow_reason_is_empty(settings):
    d = budgets.check(SESSION, IP, settings=settings)
    assert d.verdict is Verdict.ALLOW
    assert d.reason == ""


# --- the acceptance property: no SEQUENCE of requests exceeds the global cap -


def test_no_sequence_of_requests_exceeds_global_cap(settings):
    # Drive the real check-then-record loop sequentially: only spend when the
    # gate ALLOWs, recording each cost before the next check. Per the D11
    # concurrency decision (DECISIONS.md 2026-07-05), the gate is a pre-flight
    # read that doesn't know the pending cost, so the LAST allowed request
    # overshoots by at most one request's cost — the sequential (×1) case of
    # the accepted, bounded overshoot. The invariant: (1) the gate NEVER ALLOWs
    # once spend is at/over the cap, so total ≤ cap + one_request_cost; (2) once
    # tripped, every later request gets REPLAY, never ALLOW.
    cost_per_request = 0.03
    cap = settings.global_daily_spend_cap_usd
    hit_replay = False
    spend_at_last_allow = 0.0
    for i in range(200):  # far more than the cap permits
        before = traces.spend_today(settings=settings)
        decision = budgets.check(f"seq{i}", f"192.0.2.{i % 250}", settings=settings)
        if decision.verdict is Verdict.REPLAY:
            hit_replay = True
            # Once tripped, it must stay tripped for a fresh identity.
            assert budgets.check("fresh", "198.51.100.1", settings=settings).verdict is (
                Verdict.REPLAY
            )
            break
        if decision.verdict is Verdict.DENY:
            continue
        # ALLOW must never happen once spend already reached the cap.
        assert before < cap, f"ALLOWed at spend {before} >= cap {cap}"
        spend_at_last_allow = before
        spend(settings, cost=cost_per_request, session=f"seq{i}", ip=f"192.0.2.{i % 250}")
    assert hit_replay, "global cap never tripped"
    total = traces.spend_today(settings=settings)
    # Bounded overshoot: never more than one request's cost past the cap.
    assert total <= cap + cost_per_request
    # The last ALLOW was granted strictly below the cap (no ALLOW at/over cap).
    assert spend_at_last_allow < cap
