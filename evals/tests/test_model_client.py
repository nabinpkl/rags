"""The shared model client, with a stubbed SDK: no test calls a real API."""

from collections import Counter
from types import SimpleNamespace

import pytest
from askrag.config import Settings
from pydantic import SecretStr

from evals.model_client import MessagesClient


def test_a_reply_without_usage_fails_one_draft_not_the_run():
    reply = SimpleNamespace(usage=None, content=None)
    sdk = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: reply))
    client = MessagesClient(sdk, Counter())  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="no usage"):
        client.complete("m", "system", "user", 10)


def test_a_priced_call_returns_the_billed_cost_from_the_reply():
    usage = SimpleNamespace(input_tokens=5, output_tokens=3, cost=2.5e-05)
    reply = SimpleNamespace(usage=usage, content=[SimpleNamespace(type="text", text="query")])
    sdk = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: reply))
    client = MessagesClient(sdk, Counter())  # ty: ignore[invalid-argument-type]
    assert client.complete_priced("m", "system", "user", 10) == ("query", 2.5e-05)


def test_the_anthropic_host_needs_its_own_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        MessagesClient.anthropic(Settings(anthropic_api_key=SecretStr("")))
