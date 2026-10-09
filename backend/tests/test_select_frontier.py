"""select_frontier: the index manifest, and the rule that produced it."""

import json
from pathlib import Path

import pytest

from askrag import db
from askrag.ingest.select_frontier import (
    FrontierError,
    read_frontier,
    run,
    select,
    unanswerable_ids,
)

# 3 citers of PPO, 2 of DeepSeekMath, 1 of Adam — a clear ranking with a tie
# to break and a citer list longer than a small sample cap.
EDGES = [
    ("2608.00003", "1707.06347"),
    ("2608.00001", "1707.06347"),
    ("2608.00002", "1707.06347"),
    ("2608.00001", "2402.03300"),
    ("2608.00002", "2402.03300"),
    ("2608.00001", "1412.06980"),
]


def test_cited_works_rank_by_citer_count() -> None:
    frontier = select(EDGES, top_cited=3, citers_per_work=8)

    assert frontier.cited_works == ["1707.06347", "2402.03300", "1412.06980"]


def test_top_cited_bounds_the_page_scope() -> None:
    frontier = select(EDGES, top_cited=2, citers_per_work=8)

    assert frontier.cited_works == ["1707.06347", "2402.03300"]
    assert "1412.06980" not in frontier.citers


def test_citers_are_sampled_newest_first() -> None:
    """An arXiv id sorts chronologically, so 'newest' needs no date lookup.

    The page says "2 of 3"; which 2 must follow a rule a reader can restate.
    """
    frontier = select(EDGES, top_cited=1, citers_per_work=2)

    assert frontier.citers["1707.06347"] == ["2608.00003", "2608.00002"]


def test_paper_ids_cover_every_claim_the_page_makes() -> None:
    """The manifest's whole point: everything named is everything indexed."""
    frontier = select(EDGES, top_cited=2, citers_per_work=2)

    ids = set(frontier.paper_ids)
    assert set(frontier.cited_works) <= ids
    for sample in frontier.citers.values():
        assert set(sample) <= ids
    assert frontier.paper_ids == sorted(ids)


def test_a_work_cited_twice_by_one_paper_counts_its_citers_once() -> None:
    frontier = select(
        [("2608.00001", "1707.06347"), ("2608.00001", "1707.06347")],
        top_cited=1,
        citers_per_work=8,
    )

    assert frontier.citers["1707.06347"] == ["2608.00001"]


def test_run_writes_the_rule_alongside_its_result(tmp_path: Path) -> None:
    citations = tmp_path / "citations.tsv"
    citations.write_text("".join(f"{a}\t{b}\n" for a, b in EDGES), encoding="utf-8")
    frontier_path = tmp_path / "frontier.json"

    frontier = run(citations, frontier_path, top_cited=2, citers_per_work=2)

    record = json.loads(frontier_path.read_text(encoding="utf-8"))
    # The artifact is self-describing: a reader can tell what produced the list
    # without reading select_frontier.py.
    assert record["rule"] == {
        "top_cited": 2,
        "citers_per_work": 2,
        "citer_order": "newest first, by arxiv_id descending",
    }
    assert record["paper_ids"] == frontier.paper_ids
    assert read_frontier(frontier_path) == frontier
    assert not frontier_path.with_suffix(".json.tmp").exists()


def test_empty_graph_yields_an_empty_frontier() -> None:
    frontier = select([], top_cited=50, citers_per_work=8)

    assert frontier.cited_works == []
    assert frontier.paper_ids == []


def _corpus_with(tmp_path: Path, indexed_ids: list[str]) -> Path:
    """A corpus.db where exactly `indexed_ids` have chunks."""
    from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db

    def paper(arxiv_id: str) -> PaperRow:
        return PaperRow(
            arxiv_id=arxiv_id,
            title="t",
            authors="a",
            abstract="x",
            categories="cs.LG",
            published="2024-01-01",
            version="v1",
            license=None,
            venue=None,
            authority=None,
            niche_idf=None,
            author_novelty=None,
            revisions=None,
            venue_rigor=None,
        )

    path = tmp_path / "corpus.db"
    _write_corpus_db(
        path,
        [paper(i) for i in indexed_ids],
        [ChunkRow(f"{i}#0", i, "__paper__", 1, 1, "text", 2) for i in indexed_ids],
    )
    return path


def test_verify_reports_nothing_when_every_manifest_paper_is_indexed(tmp_path: Path) -> None:
    """THE invariant the inversion buys: the page names it, so the agent reads it."""
    frontier = select(EDGES, top_cited=2, citers_per_work=2)
    conn = db.connect_corpus(_corpus_with(tmp_path, frontier.paper_ids))
    try:
        assert unanswerable_ids(conn, frontier) == []
    finally:
        conn.close()


def test_verify_names_the_papers_whose_links_would_dead_end(tmp_path: Path) -> None:
    frontier = select(EDGES, top_cited=2, citers_per_work=2)
    covered = frontier.paper_ids[:-1]
    conn = db.connect_corpus(_corpus_with(tmp_path, covered))
    try:
        assert unanswerable_ids(conn, frontier) == [frontier.paper_ids[-1]]
    finally:
        conn.close()


def test_verify_on_an_empty_manifest_is_vacuously_fine(tmp_path: Path) -> None:
    conn = db.connect_corpus(_corpus_with(tmp_path, ["2401.00001"]))
    try:
        assert unanswerable_ids(conn, select([], top_cited=50, citers_per_work=8)) == []
    finally:
        conn.close()


def test_a_missing_manifest_says_which_command_makes_one(tmp_path: Path) -> None:
    """`--frontier` and `--verify` both read it; the error must name the fix."""
    with pytest.raises(FrontierError, match="run `just frontier`"):
        read_frontier(tmp_path / "frontier.json")
