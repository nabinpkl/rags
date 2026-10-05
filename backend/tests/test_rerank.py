"""Reranking (D8): order by the cross-encoder's score, keep k, fail loud on
a short score list. A scripted scorer stands in for the model."""

import pytest

from askrag.config import Settings
from askrag.retrieval.rerank import Reranker


class Scorer:
    def __init__(self, by_text: dict[str, float]) -> None:
        self.by_text = by_text
        self.seen: list[tuple[str, str]] = []

    def predict(self, sentences, batch_size):
        self.seen = list(sentences)
        return [self.by_text.get(text, 0.0) for _, text in sentences]


CANDIDATES = [("p#1", "alpha"), ("p#2", "beta"), ("p#3", "gamma")]


def test_orders_by_score_and_keeps_k():
    scorer = Scorer({"alpha": 0.1, "beta": 0.9, "gamma": 0.5})
    assert Reranker(Settings(), scorer).rerank("q", CANDIDATES, 2) == ["p#2", "p#3"]
    assert scorer.seen[0] == ("q", "alpha")


def test_ties_keep_the_retrievers_order():
    assert Reranker(Settings(), Scorer({})).rerank("q", CANDIDATES, 3) == ["p#1", "p#2", "p#3"]


def test_no_candidates_needs_no_model_call():
    scorer = Scorer({})
    assert Reranker(Settings(), scorer).rerank("q", [], 10) == []
    assert scorer.seen == []


def test_a_short_score_list_raises():
    class Short(Scorer):
        def predict(self, sentences, batch_size):
            return [1.0]

    with pytest.raises(ValueError, match="scored 1 of 3"):
        Reranker(Settings(), Short({})).rerank("q", CANDIDATES, 2)


def test_an_unpinned_model_is_refused():
    with pytest.raises(ValueError, match="pin"):
        Reranker(Settings(rerank_model_revision=""), Scorer({}))
