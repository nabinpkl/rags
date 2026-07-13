"""D11 layered budget cascade — the server-side pre-flight gate on a live agent
turn. Enforced by construction so a public, anonymous endpoint can't surprise-
bill the owner (§6 denial-of-wallet defense).

``check(session, ip)`` is a PURE read-only gate: it reads current spend/counts
from traces.py (never re-querying the DB directly) and returns a typed verdict.
The cascade, in order:

    per-session message count   → DENY   (D11: session budget is ~N messages)
    per-IP daily spend          → DENY
    global daily spend ($0.50)  → REPLAY (degrade to a cached showcase, not an
                                          error — the site stays a good demo)

The per-message TOKEN budget (config.message_token_budget) is NOT a layer here:
a turn's token count is unknown pre-flight and is enforced inside the loop (#23)
by the step/token cap. This gate governs the spend/count caps that are knowable
before the turn runs.

Concurrency (DECISIONS.md 2026-07-05): real cost is known only post-call and
written by record_run() afterward, so check-then-record has a window. This gate
is SEQUENTIALLY correct — no *sequence* of requests can exceed the global cap.
Concurrent in-flight requests can overshoot by at most (in-flight count) ×
(per-message cost cap), accepted as bounded per D11 and tightened at #23/#30 if
real abuse warrants a reserve-or-serialize step.
"""

from dataclasses import dataclass
from enum import Enum

from askrag import traces
from askrag.config import Settings, get_settings


class Verdict(Enum):
    """The three server-side outcomes of the budget gate (D11)."""

    ALLOW = "allow"
    DENY = "deny"  # a per-user cap tripped; the visitor can retry later
    REPLAY = "replay"  # global cap spent; degrade to a cached showcase session


@dataclass(frozen=True)
class BudgetDecision:
    """A typed, discriminated gate result. ``reason`` is a user-displayable,
    single-line string for DENY/REPLAY and empty for ALLOW."""

    verdict: Verdict
    reason: str = ""


_ALLOW = BudgetDecision(Verdict.ALLOW)


def check(session_id: str, ip: str, *, settings: Settings | None = None) -> BudgetDecision:
    """Pre-flight budget gate for one live agent turn (D11).

    Order matters: per-user caps (session, IP) DENY the individual; the global
    cap is the backstop and flips the whole site to REPLAY. The global check
    comes last so a fresh session/IP still gets REPLAY (not ALLOW) once the
    day's budget is spent.
    """
    settings = settings if settings is not None else get_settings()

    if (
        traces.message_count_for_session(session_id, settings=settings)
        >= settings.session_message_cap
    ):
        return BudgetDecision(
            Verdict.DENY,
            f"This session reached its {settings.session_message_cap}-message limit. "
            "Start a new session to continue.",
        )

    ip_hash = traces.hash_ip(ip, settings=settings)
    if traces.spend_for_ip_today(ip_hash, settings=settings) >= settings.ip_daily_spend_cap_usd:
        return BudgetDecision(
            Verdict.DENY,
            "You've reached today's usage limit for your network. Please try again tomorrow.",
        )

    if traces.spend_today(settings=settings) >= settings.global_daily_spend_cap_usd:
        return BudgetDecision(
            Verdict.REPLAY,
            "The live demo's daily budget is spent — showing a recorded session instead. "
            "Live chat resumes tomorrow.",
        )

    return _ALLOW
