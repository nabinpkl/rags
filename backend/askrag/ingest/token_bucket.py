"""Paces token spend against a provider's per-minute rate limit.

Why this exists rather than a sliding window over recent spend: a window
treats an empty history as free capacity, so the first seconds of a bulk run
go out at whatever the network allows. Measured 2026-09-18 against
`perplexity/pplx-embed-v1-0.6b` via OpenRouter, a 1.9M-tokens/minute target
implemented that way sent 1.1M tokens in its first 15 seconds (a 4.6M/min
rate) and drew five 429s, all inside the first five minutes; the remaining
11M tokens at a steady 1.88M/min drew none. The burst, not the average, is
what the provider refuses.

So this bucket banks NOTHING. Each `take` reserves its tokens forward in
time, and an idle stretch accrues no credit to spend later, which means at
most one request ever runs ahead of schedule instead of a whole opening
minute's worth.
"""

import time
from collections.abc import Callable


class TokenBucket:
    """Reserve `tokens` before spending them; block until the rate allows it."""

    def __init__(
        self,
        tokens_per_minute: int,
        *,
        monotonic: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if tokens_per_minute <= 0:
            raise ValueError("tokens_per_minute must be positive")
        # Injected clock/sleep are the test seam: pacing is a timing contract,
        # and a test that proves it by actually waiting is a slow test.
        # Resolved HERE rather than as default arguments, which would bind
        # `time.sleep` once at import and ignore a later patch of it.
        self._monotonic = monotonic if monotonic is not None else time.monotonic
        self._sleep = sleep if sleep is not None else time.sleep
        self._per_second = tokens_per_minute / 60.0
        self._free_at = self._monotonic()

    def take(self, tokens: int) -> float:
        """Block until `tokens` may be spent. Returns the seconds waited."""
        if tokens < 0:
            raise ValueError("tokens must not be negative")
        now = self._monotonic()
        waited = max(self._free_at - now, 0.0)
        # `max(..., now)` is what refuses to bank: time spent idle is gone,
        # not credit toward a later burst.
        self._free_at = max(self._free_at, now) + tokens / self._per_second
        if waited > 0:
            self._sleep(waited)
        return waited
