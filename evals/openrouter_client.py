"""The model client the golden drafter and the query rewriter share: OpenRouter's
Anthropic-compatible endpoint through the anthropic SDK, with token and cost
accounting."""

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

import anthropic
from askrag.config import Settings


class ModelClient(Protocol):
    def complete_nonempty(self, model: str, system: str, user: str, max_tokens: int) -> str: ...


@dataclass
class OpenRouterClient:
    """OpenRouter's Anthropic-compatible endpoint, the same seam the agent's
    smoke path uses, so one SDK reaches both model families."""

    client: anthropic.Anthropic
    usage: Counter[str]

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenRouterClient":
        key = settings.openrouter_api_key.get_secret_value()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        client = anthropic.Anthropic(base_url=settings.golden_api_base_url, api_key=key)
        return cls(client, Counter())

    def complete(self, model: str, system: str, user: str, max_tokens: int) -> str:
        return self.complete_priced(model, system, user, max_tokens)[0]

    def complete_priced(
        self, model: str, system: str, user: str, max_tokens: int
    ) -> tuple[str, float | None]:
        """The reply text and OpenRouter's billed dollars (`usage.cost`, kept
        by the SDK as an extra field), or None where the reply has no price."""
        response = self.client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
        )
        # A 200 without usage or content is a malformed provider reply (seen
        # from stealth/space-bunny-alpha, 2026-10-05): one failed draft, not a
        # crash of the whole run.
        if response.usage is None or response.content is None:
            raise ValueError(f"{model} returned a reply with no usage or content")
        self.usage[f"{model} in"] += response.usage.input_tokens
        self.usage[f"{model} out"] += response.usage.output_tokens
        cost = getattr(response.usage, "cost", None)
        text = "".join(b.text for b in response.content if b.type == "text")
        return text, float(cost) if isinstance(cost, int | float) else None

    def complete_nonempty(self, model: str, system: str, user: str, max_tokens: int) -> str:
        """One retry on an empty text block: a reasoning model sometimes ends
        on thinking alone (1 of 12 calls in the first smoke run)."""
        return self.complete(model, system, user, max_tokens) or self.complete(
            model, system, user, max_tokens
        )
