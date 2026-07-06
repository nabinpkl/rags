"""Tests for askrag.tools.read_paper — word/quote-capped spans, never full
text (§5/§6c)."""

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


def test_returns_spans_in_page_order(corpus_db):
    result = run(ReadPaperArgs(paper_id="2401.00001"), corpus_db_path=corpus_db)
    assert result.paper_id == "2401.00001"
    assert [s.section for s in result.spans] == ["Intro", "Method", "Results"]


def test_result_is_capped_to_max_quotes_per_paper(corpus_db):
    # 4 chunks exist; the cap only lets 3 through, and says so.
    result = run(
        ReadPaperArgs(paper_id="2401.00001"),
        settings=Settings(max_quotes_per_paper=3),
        corpus_db_path=corpus_db,
    )
    assert len(result.spans) == 3
    assert result.spans_available == 4


def test_each_span_is_truncated_to_quote_max_words(corpus_db):
    result = run(
        ReadPaperArgs(paper_id="2401.00001"),
        settings=Settings(quote_max_words=2, max_quotes_per_paper=10),
        corpus_db_path=corpus_db,
    )
    first = result.spans[0]
    assert first.text == "one two"
    assert first.truncated is True


def test_a_span_at_or_under_the_word_cap_is_not_marked_truncated(corpus_db):
    result = run(
        ReadPaperArgs(paper_id="2401.00001"),
        settings=Settings(quote_max_words=50, max_quotes_per_paper=10),
        corpus_db_path=corpus_db,
    )
    assert all(not s.truncated for s in result.spans)


def test_page_range_filters_to_overlapping_chunks(corpus_db):
    result = run(
        ReadPaperArgs(paper_id="2401.00001", page_start=2, page_end=3),
        settings=Settings(max_quotes_per_paper=10),
        corpus_db_path=corpus_db,
    )
    assert [s.section for s in result.spans] == ["Method"]


def test_never_returns_more_words_than_the_cap_allows_total(corpus_db):
    # No combination of page range + quote caps can reconstruct the paper:
    # total words returned <= max_quotes_per_paper * quote_max_words.
    result = run(
        ReadPaperArgs(paper_id="2401.00001"),
        settings=Settings(quote_max_words=2, max_quotes_per_paper=2),
        corpus_db_path=corpus_db,
    )
    total_words = sum(len(s.text.split()) for s in result.spans)
    assert total_words <= 2 * 2
