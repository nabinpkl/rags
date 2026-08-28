"""extract_citations: which reference forms count, and which must not."""

from pathlib import Path

import pytest

from askrag.ingest.extract_citations import (
    CitationExtractError,
    cited_ids,
    newest_id_month,
    read_citations,
    run,
)

CITING = "2608.01234"
CEILING = "2608"


def _cited(body: str, citing_id: str = CITING) -> set[str]:
    return cited_ids(body, citing_id=citing_id, newest_id_month=CEILING)


def _write(text_dir: Path, arxiv_id: str, body: str) -> None:
    month = text_dir / arxiv_id[:4]
    month.mkdir(parents=True, exist_ok=True)
    (month / f"{arxiv_id}.txt").write_text(body, encoding="utf-8")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # THE regression case. The canonical spelling capitalizes the X, and a
        # case-sensitive pattern drops roughly two thirds of all real
        # references while still returning a plausible-looking edge count.
        ("see arXiv:2505.09388 for details", {"2505.09388"}),
        ("see arxiv:2505.09388", {"2505.09388"}),
        ("see ARXIV:2505.09388", {"2505.09388"}),
        ("https://arxiv.org/abs/2505.09388", {"2505.09388"}),
        ("https://arxiv.org/pdf/2505.09388v2", {"2505.09388"}),
        ("arXiv preprint arXiv:2402.03300", {"2402.03300"}),
        # The extractor wraps long URLs mid-token; a reference split across a
        # line break is the same reference.
        ("arXiv:\n2505.09388", {"2505.09388"}),
        # Bare ids: many bibliography styles drop the marker entirely.
        ("Qwen3 Technical Report. 2505.09388. 2025.", {"2505.09388"}),
        # Four-digit id-months are 5-digit-suffixed too (post-2015 volume).
        ("arXiv:0704.0001", {"0704.0001"}),
        ("", set()),
    ],
)
def test_recognized_forms(body: str, expected: set[str]) -> None:
    assert _cited(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        # Predates the first new-style id-month (2007-04).
        "arXiv:0703.12345",
        # Old-style ids are out of scope (documented in the module docstring)
        # — absent from the graph, never miscounted into it.
        "cs/0701001",
        # Too few / too many suffix digits to be an arXiv id.
        "2505.093",
        # Embedded in a longer digit run.
        "12505.093881",
        # A YEAR followed by a number. Month 23 cannot exist, and this shape is
        # everywhere in bibliographies ("Proceedings of ICML, 2023. 00092").
        "Proceedings of ICML, 2023. 00092",
        "2019.0352",
        "1688.12609",
        # Month 00 is not a month either.
        "2600.12345",
        # Postdates the newest month we hold: nothing could have cited it.
        "arXiv:2612.00001",
    ],
)
def test_rejected_forms(body: str) -> None:
    assert _cited(body) == set()


def test_same_month_citation_is_kept() -> None:
    """The ceiling is inclusive: papers do cite others from their own month."""
    assert _cited("arXiv:2608.00001") == {"2608.00001"}


def test_a_revised_paper_may_cite_a_later_month() -> None:
    """We extract the LATEST version's text.

    A July paper revised in September genuinely cites August work, so the
    ceiling is the corpus's newest month — not the citing paper's own.
    """
    assert _cited("arXiv:2608.01880", citing_id="2607.02501") == {"2608.01880"}


def test_newest_id_month_comes_from_the_corpus() -> None:
    paths = [Path("text/2607/2607.00001.txt"), Path("text/2608/2608.09999.txt")]
    assert newest_id_month(paths) == "2608"
    assert newest_id_month([]) == "0704"


def test_self_citation_is_dropped() -> None:
    body = f"our earlier version, arXiv:{CITING}, and arXiv:2505.09388"
    assert _cited(body) == {"2505.09388"}


def test_repeated_reference_counts_once() -> None:
    body = "arXiv:2505.09388 ... as shown in arXiv:2505.09388 ... arxiv.org/abs/2505.09388"
    assert _cited(body) == {"2505.09388"}


def test_run_writes_a_sorted_edge_list(tmp_path: Path) -> None:
    text_dir = tmp_path / "text"
    _write(text_dir, "2608.00002", "arXiv:2505.09388 and arXiv:2402.03300")
    _write(text_dir, "2608.00001", "arXiv:2505.09388")
    _write(text_dir, "2607.00001", "no references here")
    citations_path = tmp_path / "citations.tsv"

    stats = run(text_dir, citations_path)

    assert stats.papers_scanned == 3
    assert stats.papers_with_citations == 2
    assert stats.edges == 3
    assert stats.distinct_cited == 2
    # Stable order so the artifact is diffable across runs.
    assert read_citations(citations_path) == [
        ("2608.00001", "2505.09388"),
        ("2608.00002", "2402.03300"),
        ("2608.00002", "2505.09388"),
    ]


def test_run_refuses_a_missing_text_tree(tmp_path: Path) -> None:
    with pytest.raises(CitationExtractError, match="no extracted-text tree"):
        run(tmp_path / "absent", tmp_path / "citations.tsv")


def test_read_citations_refuses_a_missing_edge_list(tmp_path: Path) -> None:
    with pytest.raises(CitationExtractError, match="run extract_citations first"):
        read_citations(tmp_path / "citations.tsv")


def test_partial_write_is_not_left_behind(tmp_path: Path) -> None:
    """tmp+rename: the .tmp scratch file never survives a completed run."""
    text_dir = tmp_path / "text"
    _write(text_dir, "2608.00001", "arXiv:2505.09388")
    citations_path = tmp_path / "citations.tsv"

    run(text_dir, citations_path)

    assert citations_path.exists()
    assert not citations_path.with_suffix(".tsv.tmp").exists()
