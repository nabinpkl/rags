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
    kw = dict(seed=1, rare_max_df=40, mismatch_max_df=500, multi_hop_min_shared=0)
    first = sample_sources(chunks, Counter(), quota, **kw)
    again = sample_sources(chunks, Counter(), quota, **kw)
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
        chunks,
        Counter(),
        {GoldenType.MULTI_HOP.value: 1},
        seed=0,
        rare_max_df=40,
        mismatch_max_df=500,
        multi_hop_min_shared=1,
    )
    assert len(sources) == 1
    pair = sources[0].chunks
    assert pair[0].paper_id == pair[1].paper_id
    assert pair[0].section != pair[1].section


def multi_hop(chunks, min_shared):
    df = Counter({"we": 99, "the": 99, "on": 99, "report": 99})
    return sample_sources(
        chunks,
        df,
        {GoldenType.MULTI_HOP.value: 1},
        seed=0,
        rare_max_df=40,
        mismatch_max_df=500,
        multi_hop_min_shared=min_shared,
    )


def test_multi_hop_pairs_the_section_naming_the_same_things():
    chunks = [
        chunk("1.1#0", "cl", "we train GRPO policies on MathBench", section="Method"),
        chunk("1.1#1", "cl", "the GRPO policies win on MathBench", section="Results"),
        chunk("1.1#2", "cl", "we report funding and ethics", section="Ethics"),
    ]
    [source] = multi_hop(chunks, 3)
    assert {c.chunk_id for c in source.chunks} == {"1.1#0", "1.1#1"}


def test_a_chunk_without_a_related_section_is_never_paired():
    chunks = [
        chunk("1.1#0", "cl", "we train GRPO policies", section="Method"),
        chunk("1.1#1", "cl", "we report funding and ethics", section="Ethics"),
    ]
    assert multi_hop(chunks, 2) == []


def test_a_summary_section_is_never_half_of_a_pair():
    chunks = [
        chunk("1.1#0", "cl", "we train GRPO policies on MathBench", section="1 Introduction"),
        chunk("1.1#1", "cl", "the GRPO policies win on MathBench", section="Results"),
    ]
    assert multi_hop(chunks, 3) == []


def test_vocabulary_mismatch_bars_words_under_the_wider_bar_and_moves_nothing():
    chunks = [
        chunk(f"{p}.0001#1", "cl", f"we train robots with GRPO and grokking {p}")
        for p in range(1, 7)
    ]
    df = Counter({"train": 2000, "robot": 300, "grokking": 3, "grpo": 6})
    base = {GoldenType.EXACT_MATCH.value: 2}
    widened = {**base, GoldenType.VOCABULARY_MISMATCH.value: 2}
    kw = dict(seed=3, rare_max_df=40, mismatch_max_df=500, multi_hop_min_shared=0)
    before = sample_sources(chunks, df, base, **kw)
    after = sample_sources(chunks, df, widened, **kw)
    assert [s.chunks for s in after[:2]] == [s.chunks for s in before]
    mismatch = [s for s in after if s.type is GoldenType.VOCABULARY_MISMATCH]
    assert len(mismatch) == 2
    assert {"robot", "grokking", "grpo"} <= mismatch[0].rare_terms
    assert "train" not in mismatch[0].rare_terms
