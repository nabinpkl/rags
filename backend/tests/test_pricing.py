"""Tests for askrag.agent.pricing — what a turn cost, in dollars.

Security-relevant per §6 (denial-of-wallet): this number is what D11's caps
are compared against, so the failure that matters is UNDER-reporting — a turn
priced below what it really cost lets spend past a gate that should have
stopped it. Every case below pins which of the two sources won.
"""

from dataclasses import dataclass

from askrag.agent.pricing import TurnCost
from askrag.config import Settings


def settings(**overrides):
    return Settings(_env_file=None, **overrides)  # ty: ignore[unknown-argument]


@dataclass
class FakeUsage:
    """The Anthropic-shaped usage object. `cost` is OpenRouter's extra, which
    the SDK preserves as a pydantic extra field (verified 2026-08-11); real
    Anthropic responses simply have no such attribute."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None


@dataclass
class FakeUsageWithCost(FakeUsage):
    cost: object = 0.0


def test_no_calls_costs_nothing():
    assert TurnCost().usd(settings()) == 0.0


def test_provider_reported_cost_wins_over_the_rate_table():
    # Rates that would compute a wildly different number, so the assertion can
    # only pass if the provider's figure is the one used.
    cost = TurnCost()
    cost.add(FakeUsageWithCost(input_tokens=1_000_000, output_tokens=1_000_000, cost=0.000021))
    assert cost.usd(settings(agent_usd_per_mtok_in=1.0, agent_usd_per_mtok_out=5.0)) == 0.000021


def test_provider_costs_sum_across_steps():
    cost = TurnCost()
    for _ in range(3):
        cost.add(FakeUsageWithCost(input_tokens=10, output_tokens=5, cost=0.001))
    assert cost.usd(settings()) == 0.003
    assert cost.calls == 3


def test_falls_back_to_the_rate_table_when_the_provider_is_silent():
    """The prod path (D3): real Anthropic sends no cost field."""
    cost = TurnCost()
    cost.add(FakeUsage(input_tokens=1_000_000, output_tokens=1_000_000))
    s = settings(agent_usd_per_mtok_in=1.0, agent_usd_per_mtok_out=5.0)
    assert cost.usd(s) == 6.0


def test_cache_tiers_price_separately_in_the_fallback():
    cost = TurnCost()
    cost.add(
        FakeUsage(
            input_tokens=1_000_000,
            output_tokens=0,
            cache_creation_input_tokens=1_000_000,
            cache_read_input_tokens=2_000_000,
        )
    )
    s = settings(
        agent_usd_per_mtok_in=1.0, agent_usd_per_mtok_out=5.0, agent_usd_per_mtok_cache_read=0.1
    )
    # fresh_in = input + cache_creation = 2M @ $1; cache_read = 2M @ $0.10
    assert cost.usd(s) == 2.0 + 0.2


def test_a_mixed_turn_prices_from_the_table_not_a_partial_sum():
    """One unpriced call falsifies the whole turn: summing only the calls that
    reported would under-report, which is the one direction D11 can't take."""
    cost = TurnCost()
    cost.add(FakeUsageWithCost(input_tokens=1_000_000, output_tokens=0, cost=0.000001))
    cost.add(FakeUsage(input_tokens=1_000_000, output_tokens=0))
    assert cost.usd(settings(agent_usd_per_mtok_in=1.0)) == 2.0


def test_unusable_cost_values_are_treated_as_unreported():
    """bool is an int subclass, and a negative cost is a provider bug rather
    than a discount — neither may be trusted as a dollar figure."""
    # NaN matters most: `nan > cap` is False, so a poisoned turn would never
    # trip a limit.
    for bad in (None, "0.01", True, -0.5, float("nan"), float("inf")):
        cost = TurnCost()
        cost.add(FakeUsageWithCost(input_tokens=1_000_000, output_tokens=0, cost=bad))
        assert cost.usd(settings(agent_usd_per_mtok_in=1.0)) == 1.0, bad


def test_zero_is_a_real_reported_cost_not_a_missing_one():
    """A free/promotional generation genuinely costs nothing; that must not be
    mistaken for 'the provider said nothing' and re-priced at Haiku rates."""
    cost = TurnCost()
    cost.add(FakeUsageWithCost(input_tokens=1_000_000, output_tokens=0, cost=0.0))
    assert cost.usd(settings(agent_usd_per_mtok_in=1.0)) == 0.0


def test_token_totals_are_billing_tier_agnostic():
    cost = TurnCost()
    cost.add(
        FakeUsage(
            input_tokens=100,
            output_tokens=10,
            cache_creation_input_tokens=5,
            cache_read_input_tokens=20,
        )
    )
    assert cost.fresh_in == 105
    assert cost.cache_read == 20
    assert cost.tokens_in == 125
    assert cost.tokens_total == 135
