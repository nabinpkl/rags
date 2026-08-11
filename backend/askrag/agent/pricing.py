"""What one turn cost, in dollars (D3/§7, feeding D11's caps).

Two sources of truth, in priority order:

1. **The provider's own number.** OpenRouter returns `usage.cost` — the exact
   amount it billed — on every response, and the Anthropic SDK preserves it as
   a pydantic extra. When it is there, it IS the cost: no rate table to keep in
   sync with a model id, no drift when a model is repriced.
2. **`config.py`'s rate table.** Real Anthropic sends no cost field (D3, the
   prod path), so Haiku turns are priced from `agent_usd_per_mtok_*` exactly as
   before.

Mixed turns price from the table, never a half-provider/half-table sum: a
partial provider total silently *under*-reports, and under-reporting is the one
error direction D11's caps cannot tolerate (spend passes the gate that should
have stopped it).
"""

import math
from dataclasses import dataclass, field
from typing import Any

from askrag.config import Settings


@dataclass
class TurnCost:
    """Accumulates one turn's usage across every model call it makes.

    Token counters are billing-tier-aware: `fresh_in` (input + cache creation)
    bills at the full input rate, `cache_read` at the reduced one (D3 prompt
    caching). Both are real context, so both count toward the token budget —
    only the price differs.
    """

    fresh_in: int = 0
    out: int = 0
    cache_read: int = 0
    provider_usd: float = 0.0
    calls: int = 0
    # Vacuously true; the first unpriced response falsifies it for the turn.
    every_call_priced: bool = field(default=True)

    def add(self, usage: Any) -> None:
        self.calls += 1
        self.fresh_in += usage.input_tokens + (usage.cache_creation_input_tokens or 0)
        self.out += usage.output_tokens
        self.cache_read += usage.cache_read_input_tokens or 0

        reported = getattr(usage, "cost", None)
        # A dollar figure must be a finite, non-negative number. bool is an int
        # subclass; a negative cost is a provider bug rather than a discount;
        # NaN would poison every comparison D11's caps make (NaN > cap is
        # False, so a poisoned turn would never trip a limit). Each is treated
        # as "did not report", falling the turn back to the rate table.
        if (
            isinstance(reported, bool)
            or not isinstance(reported, int | float)
            or not math.isfinite(reported)
            or reported < 0
        ):
            self.every_call_priced = False
            return
        self.provider_usd += float(reported)

    @property
    def tokens_in(self) -> int:
        """The persisted/reported input total, billing-tier-agnostic."""
        return self.fresh_in + self.cache_read

    @property
    def tokens_total(self) -> int:
        """Everything that occupied context this turn — what the token budget
        is measured against."""
        return self.fresh_in + self.cache_read + self.out

    def usd(self, settings: Settings) -> float:
        if self.calls == 0:
            return 0.0
        if self.every_call_priced:
            return self.provider_usd
        return (
            self.fresh_in / 1_000_000 * settings.agent_usd_per_mtok_in
            + self.out / 1_000_000 * settings.agent_usd_per_mtok_out
            + self.cache_read / 1_000_000 * settings.agent_usd_per_mtok_cache_read
        )
