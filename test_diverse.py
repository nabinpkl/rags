"""Unit tests for the diverse-sample pure logic (no network, no DB)."""
import math

import arxiv_ingest as ai


# --- venue extraction -------------------------------------------------------

def test_venue_comments_accepted_top_venue():
    v, t = ai.extract_venue("", "", "12 pages, accepted to NeurIPS 2023")
    assert t == 3 and v == "NEURIPS"


def test_venue_comments_bare_mention_is_weaker():
    # a venue named without an acceptance cue is only a weak hint, not tier 3
    v, t = ai.extract_venue("", "", "our method resembles the ICML baseline")
    assert t == 2


def test_venue_false_positive_rejected_is_not_top_tier():
    # "rejected from ICML" has a venue token but no acceptance cue -> not tier 3
    _, t = ai.extract_venue("", "", "note: this work was rejected from ICML")
    assert t == 2  # bare mention, not an acceptance


def test_venue_doi_acl_prefix_is_top():
    v, t = ai.extract_venue("", "10.18653/v1/2020.acl-main.1", "")
    assert t == 3 and v == "ACL"


def test_venue_doi_generic_publisher_is_floor():
    v, t = ai.extract_venue("", "10.1109/TSP.2020.123456", "")
    assert t == 1 and v == "IEEE"


def test_venue_journal_ref_top_journal():
    v, t = ai.extract_venue("JMLR 21(1):1-30, 2020", "", "")
    assert t == 3


def test_venue_none_detected():
    assert ai.extract_venue("", "", "10 pages, 3 figures") == (None, 0)


def test_venue_takes_best_across_sources():
    # generic doi (1) + accepted-NeurIPS comment (3) -> 3
    _, t = ai.extract_venue("", "10.1109/x", "accepted at NeurIPS")
    assert t == 3


def test_core_tier_augments_curated():
    core = {"recsys": 3, "wacv": 2}
    _, t = ai.extract_venue("Proceedings of RecSys 2021", "", "")
    # RecSys isn't in the curated regex, so journal-ref falls back to generic...
    assert t == 1
    # ...but a CORE-known token in a cued comment resolves via _venue_tier
    assert ai._venue_tier("recsys", core) == 3
    assert ai._venue_tier("wacv", core) == 2
    assert ai._venue_tier("unknownconf", core) == 0


# --- citation in-degree -----------------------------------------------------

def test_build_indegree_counts_values_not_keys(tmp_path):
    # A cites B,C ; B cites C. So indeg: C=2, B=1, A absent (never cited).
    f = tmp_path / "cit.json"
    f.write_text('{"A": ["B", "C"], "B": ["C"]}')
    indeg = ai.build_indegree(str(f))
    assert indeg == {"B": 1, "C": 2}
    assert "A" not in indeg  # a citing-only key is never miscounted as cited


def test_build_indegree_empty_lists(tmp_path):
    f = tmp_path / "cit.json"
    f.write_text('{"A": [], "B": ["A"]}')
    assert ai.build_indegree(str(f)) == {"A": 1}


# --- author key + tables ----------------------------------------------------

def test_author_key_normalizes():
    assert ai._author_key("LeCun", "Yann") == "lecun|y"
    assert ai._author_key("  Ng ", "A. Y.") == "ng|a"


# --- rank normalization -----------------------------------------------------

def test_rank_normalize_spreads_0_to_1():
    assert ai.rank_normalize([10, 20, 30]) == [0.0, 0.5, 1.0]


def test_rank_normalize_ties_share_mean():
    # two tied lowest share rank (0+1)/2/3 = 0.1666..., highest = 1
    out = ai.rank_normalize([5, 5, 9, 20])
    assert out[0] == out[1] == (0 + 1) / 2 / 3
    assert out[3] == 1.0


def test_rank_normalize_constant_is_half():
    assert ai.rank_normalize([7, 7, 7]) == [0.5, 0.5, 0.5]


def test_rank_normalize_edge_cases():
    assert ai.rank_normalize([]) == []
    assert ai.rank_normalize([42]) == [0.5]


# --- composite scoring ------------------------------------------------------

def _row(auth, niche, nov, rev, rig):
    return {"authority": auth, "niche_idf": niche, "author_novelty": nov,
            "revisions": rev, "venue_rigor": rig}


def test_composite_orders_by_blend():
    w = ai.DEFAULT_WEIGHTS
    rows = [_row(0, 0, 0, 1, 0),      # all-low
            _row(100, 5, 1, 5, 3)]    # all-high
    s = ai.composite_scores(rows, w)
    assert s[1] > s[0]


def test_parse_weights_overrides_defaults_only_known_keys():
    w = ai.parse_weights("authority=0.5,venue=0.1,bogus=9")
    assert w["authority"] == 0.5 and w["venue"] == 0.1
    assert "bogus" not in w
    # untouched keys keep defaults
    assert w["niche"] == ai.DEFAULT_WEIGHTS["niche"]


# --- niche idf math ---------------------------------------------------------

def test_even_sample_spans_endpoints():
    xs = list(range(100))
    picks = ai._even_sample(xs, 5)
    assert picks[0] == 0 and picks[-1] == 99 and len(picks) == 5
