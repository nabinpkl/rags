"""Reranking (D8): order by score, keep k, report the billed cost, and fail
loud on a reply out of contract. A scripted scorer and httpx's mock
transport stand in for the models; nothing here calls a provider."""

import json

import httpx
import pytest

from askrag.config import Settings
from askrag.retrieval.rerank import OpenRouterScorer, Reranker, RerankError


class Scripted:
    def __init__(self, by_text: dict[str, float], usd: float = 0.0) -> None:
        self.by_text = by_text
        self.usd = usd
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query, texts):
        self.calls.append((query, list(texts)))
        return [self.by_text.get(t, 0.0) for t in texts], self.usd


CANDIDATES = [("p#1", "alpha"), ("p#2", "beta"), ("p#3", "gamma")]


def test_orders_by_score_keeps_k_and_carries_the_cost():
    scorer = Scripted({"alpha": 0.1, "beta": 0.9, "gamma": 0.5}, usd=0.0007)
    got = Reranker(Settings(), scorer).rerank("q", CANDIDATES, 2)
    assert got.chunk_ids == ["p#2", "p#3"]
    assert got.usd == 0.0007
    assert scorer.calls == [("q", ["alpha", "beta", "gamma"])]


def test_ties_keep_the_retrievers_order():
    got = Reranker(Settings(), Scripted({})).rerank("q", CANDIDATES, 3)
    assert got.chunk_ids == ["p#1", "p#2", "p#3"]


def test_no_candidates_needs_no_model_call():
    scorer = Scripted({})
    got = Reranker(Settings(), scorer).rerank("q", [], 10)
    assert (got.chunk_ids, got.usd, scorer.calls) == ([], 0.0, [])


def test_a_short_score_list_raises():
    class Short(Scripted):
        def score(self, query, texts):
            return [1.0], 0.0

    with pytest.raises(RerankError, match="scored 1 of 3"):
        Reranker(Settings(), Short({})).rerank("q", CANDIDATES, 2)


def openrouter(handler, slept: list[float] | None = None) -> OpenRouterScorer:
    # By alias: the field reads only OPENROUTER_API_KEY, so the field name as a
    # keyword is ignored and the test would borrow the developer's real key.
    settings = Settings.model_validate({"OPENROUTER_API_KEY": "test-key", "rerank_max_attempts": 3})
    return OpenRouterScorer(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=(slept if slept is not None else []).append,
    )


def test_openrouter_scores_follow_the_input_order_and_report_cost():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        # Results arrive best first, named by input index.
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.8},
                    {"index": 0, "relevance_score": 0.3},
                ],
                "usage": {"total_tokens": 42, "cost": 8.4e-07},
            },
        )

    scores, usd = openrouter(handler).score("q", ["a", "b"])
    assert scores == [0.3, 0.8]
    assert usd == 8.4e-07
    assert seen == {"model": "voyageai/rerank-3-lite", "query": "q", "documents": ["a", "b"]}


@pytest.mark.parametrize(
    "reply",
    [
        {"results": [{"index": 0, "relevance_score": 0.3}], "usage": {"cost": 1e-6}},
        {"results": [{"index": 0, "relevance_score": 0.3}, {"index": 1, "relevance_score": 0.1}]},
    ],
    ids=["a document unscored", "no cost reported"],
)
def test_openrouter_reply_out_of_contract_raises(reply):
    scorer = openrouter(lambda request: httpx.Response(200, json=reply))
    with pytest.raises(RerankError):
        scorer.score("q", ["a", "b"])


def test_openrouter_error_status_raises():
    scorer = openrouter(lambda request: httpx.Response(404, text="guardrail"))
    with pytest.raises(RerankError, match="HTTP 404"):
        scorer.score("q", ["a"])


GOOD = {"results": [{"index": 0, "relevance_score": 0.5}], "usage": {"cost": 1e-6}}


def test_openrouter_retries_a_rate_limit_then_succeeds():
    replies = iter([httpx.Response(429, text="tpm"), httpx.Response(200, json=GOOD)])
    slept: list[float] = []
    assert openrouter(lambda request: next(replies), slept).score("q", ["a"]) == ([0.5], 1e-6)
    assert slept == [2.0]


def test_openrouter_gives_up_after_the_last_attempt():
    slept: list[float] = []
    scorer = openrouter(lambda request: httpx.Response(503, text="down"), slept)
    with pytest.raises(RerankError, match="HTTP 503"):
        scorer.score("q", ["a"])
    assert slept == [2.0, 4.0]
