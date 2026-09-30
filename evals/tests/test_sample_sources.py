"""Source sampling for the golden set: pure over chunk lists, no model."""

from collections import Counter

from evals.golden_set import GoldenType
from evals.sample_sources import (
    SourceChunk,
    anchor_term,
    is_known_hard,
    rare_terms,
    sample_sources,
    words,
)


def chunk(chunk_id: str, category: str, text: str, section: str = "Method") -> SourceChunk:
    return SourceChunk(chunk_id, chunk_id.split("#")[0], category, section, text)


def test_words_fold_plurals_and_case():
    assert words("Embeddings embedding EMBEDDING") == {"embedding"}


def test_rare_terms_are_measured_against_the_corpus():
    df = Counter({"model": 900, "show": 700, "grokking": 3})
    assert rare_terms("the model shows grokking", df, max_df=40) == {"grokking"}


def test_known_hard_detects_tables_and_math():
    assert is_known_hard("| a | b |\n| 1 | 2 |\n| 3 | 4 |")
    assert is_known_hard("$x$ $y$ $z$ \\alpha \\beta \\gamma $a$ $b$")
    assert not is_known_hard("Plain prose about a method.")


def test_anchor_must_recur_in_two_papers():
    # A running header lives in one paper only; a field term in several.
    term_df = Counter({"ASE": 9, "GRPO": 5})
    papers = Counter({"ASE": 1, "GRPO": 3})
    text = "ASE '26 ... we train with GRPO"
    assert anchor_term(text, term_df, papers, max_df=40) == "GRPO"


def test_shouted_words_and_capitalised_phrases_are_not_terms():
    term_df = Counter({"ANSWER": 3, "Low-Level": 3, "MNIST": 3})
    papers = Counter({"ANSWER": 3, "Low-Level": 3, "MNIST": 3})
    word_df = Counter({"answer": 5000, "mnist": 30})
    text = "ANSWER: the Low-Level encoder on MNIST"
    assert anchor_term(text, term_df, papers, max_df=40, word_df=word_df) == "MNIST"


def test_a_long_all_caps_word_is_not_an_acronym():
    term_df, papers = Counter({"DISTRIBUTED": 4}), Counter({"DISTRIBUTED": 4})
    assert anchor_term("the DISTRIBUTED algorithm", term_df, papers, max_df=40) is None


def test_sampling_is_seeded_stratified_and_one_per_paper():
    chunks = [
        chunk(f"{cat}{p}.0001#{i}", cat, f"prose number {i} about topic {p}")
        for cat in ("cl", "cv")
        for p in range(3)
        for i in range(2)
    ]
    quota = {GoldenType.SINGLE_HOP.value: 4}
    first = sample_sources(chunks, Counter(), quota, seed=1, rare_max_df=40)
    again = sample_sources(chunks, Counter(), quota, seed=1, rare_max_df=40)
    assert [s.chunks for s in first] == [s.chunks for s in again]
    papers = [s.chunks[0].paper_id for s in first]
    assert len(papers) == len(set(papers)) == 4
    assert {s.chunks[0].category for s in first} == {"cl", "cv"}


def test_multi_hop_pairs_two_sections_of_one_paper():
    chunks = [
        chunk("1.1#0", "cl", "setup text", section="Setup"),
        chunk("1.1#1", "cl", "results text", section="Results"),
    ]
    sources = sample_sources(
        chunks, Counter(), {GoldenType.MULTI_HOP.value: 1}, seed=0, rare_max_df=40
    )
    assert len(sources) == 1
    pair = sources[0].chunks
    assert pair[0].paper_id == pair[1].paper_id
    assert pair[0].section != pair[1].section
