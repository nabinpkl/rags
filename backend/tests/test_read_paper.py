"""Tests for askrag.tools.read_paper — page-bounded, token-budgeted spans for
the model's deep read (§5/§6c row 1).

The old "no combination of page range + quote caps can reconstruct the
paper" invariant is gone: that was the ≤50w/≤3-quote *display* cap wrongly
enforced at this tool (2026-07-06 checkpoint finding 1). This tool now
serves the model page-bounded text up to `read_paper_max_tokens`; the
display cap moved downstream (answer-assembly, #23/#30).
"""

import pytest

from askrag.config import Settings
from askrag.ingest.build_indexes import ChunkRow, PaperRow, _write_corpus_db
from askrag.tools.read_paper import ReadPaperArgs, ReadPaperError, run


def paper(arxiv_id):
    return PaperRow(
        arxiv_id=arxiv_id,
        title="t",
        authors="a",
        abstract="x",
        categories="cs.CL",
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


@pytest.fixture
def corpus_db(tmp_path):
    chunks = [
        ChunkRow("2401.00001#0", "2401.00001", "Intro", 1, 1, "one two three four five", 5),
        ChunkRow("2401.00001#1", "2401.00001", "Method", 2, 3, "six seven eight", 3),
        ChunkRow("2401.00001#2", "2401.00001", "Results", 4, 4, "nine ten", 2),
        ChunkRow("2401.00001#3", "2401.00001", "Conclusion", 5, 5, "eleven twelve", 2),
    ]
    path = tmp_path / "corpus.db"
    _write_corpus_db(path, [paper("2401.00001")], chunks)
    return path


def test_unknown_paper_id_is_refused(corpus_db):
    with pytest.raises(ReadPaperError, match="9999.99999"):
        run(ReadPaperArgs(paper_id="9999.99999"), corpus_db_path=corpus_db)


def test_returns_all_matching_spans_in_page_order_within_budget(corpus_db):
    # 5+3+2+2=12 tokens total, well under the default 16,000 budget — every
    # chunk comes back, none of them display-word-truncated.
    result = run(ReadPaperArgs(paper_id="2401.00001"), corpus_db_path=corpus_db)
    assert result.paper_id == "2401.00001"
    assert [s.section for s in result.spans] == ["Intro", "Method", "Results", "Conclusion"]
    assert result.spans_available == 4
    assert result.tokens_used == 12
    assert result.truncated is False


def test_spans_carry_full_untruncated_chunk_text(corpus_db):
    result = run(ReadPaperArgs(paper_id="2401.00001"), corpus_db_path=corpus_db)
    assert result.spans[0].text == "one two three four five"


def test_page_range_filters_to_overlapping_chunks(corpus_db):
    result = run(
        ReadPaperArgs(paper_id="2401.00001", page_start=2, page_end=3),
        corpus_db_path=corpus_db,
    )
    assert [s.section for s in result.spans] == ["Method"]


def test_ignores_the_display_caps_quote_max_words_and_max_quotes_per_paper(corpus_db):
    # These settings govern the ANSWER display cap (§6c row 4), enforced at
    # answer-assembly (#23/#30) — read_paper must not re-apply them.
    result = run(
        ReadPaperArgs(paper_id="2401.00001"),
        settings=Settings(quote_max_words=1, max_quotes_per_paper=1),
        corpus_db_path=corpus_db,
    )
    assert len(result.spans) == 4
    assert result.spans[0].text == "one two three four five"


def test_token_budget_bounds_the_returned_spans(corpus_db):
    # Intro(5) + Method(3) = 8 fits; + Results(2) = 10 would exceed 8, so the
    # prefix stops after Method.
    result = run(
        ReadPaperArgs(paper_id="2401.00001"),
        settings=Settings(read_paper_max_tokens=8),
        corpus_db_path=corpus_db,
    )
    assert [s.section for s in result.spans] == ["Intro", "Method"]
    assert result.spans_available == 4
    assert result.tokens_used == 8
    assert result.truncated is True


def test_at_least_one_span_returned_even_if_it_alone_exceeds_the_budget(corpus_db):
    result = run(
        ReadPaperArgs(paper_id="2401.00001"),
        settings=Settings(read_paper_max_tokens=2),  # Intro alone is 5 tokens
        corpus_db_path=corpus_db,
    )
    assert [s.section for s in result.spans] == ["Intro"]
    assert result.tokens_used == 5
    assert result.truncated is True


def test_to_model_payload_is_a_plain_dict_of_the_result(corpus_db):
    result = run(
        ReadPaperArgs(paper_id="2401.00001", page_start=2, page_end=3),
        corpus_db_path=corpus_db,
    )
    payload = result.to_model_payload()
    assert payload == {
        "paper_id": "2401.00001",
        "spans": [{"section": "Method", "page_start": 2, "page_end": 3, "text": "six seven eight"}],
        "spans_available": 1,
        "tokens_used": 3,
        "truncated": False,
    }


def test_a_scoped_turn_refuses_a_paper_outside_its_claim(corpus_db):
    """Scoping search without scoping direct reads leaves the scope open.

    The model can name any indexed id here, so a scoped turn must refuse the
    ones its landing-page claim does not cover.
    """
    with pytest.raises(ReadPaperError, match="outside this conversation's scope"):
        run(
            ReadPaperArgs(paper_id="2401.00001"),
            scope=("2499.99999",),
            corpus_db_path=corpus_db,
        )


def test_a_scoped_turn_reads_a_paper_inside_its_claim(corpus_db):
    result = run(
        ReadPaperArgs(paper_id="2401.00001"), scope=("2401.00001",), corpus_db_path=corpus_db
    )

    assert result.spans
