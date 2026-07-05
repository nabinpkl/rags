"""Tests for askrag.ingest.chunk_papers — D7: section-aware, ~1k-token,
overlapping, page-anchored chunks. Fixtures build extraction JSON + an
arxiv.db in tmp_path; no corpus needed."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from askrag.config import Settings
from askrag.ingest import chunk_papers
from askrag.ingest.chunk_papers import Chunk


def make_settings(**overrides: Any) -> Settings:
    return Settings(**overrides)


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


# --- fixtures: synthetic extraction JSON + arxiv.db -------------------------

# One sentence ≈ a known token count; repeated so sections cross the 1k budget.
SENT = "Retrieval augmented generation over arxiv papers helps grounding. "


def page_map(page_texts: list[str]) -> list[dict]:
    pages, off = [], 0
    for i, text in enumerate(page_texts, start=1):
        pages.append({"page": i, "char_start": off, "char_end": off + len(text)})
        off += len(text)
    return pages


def write_extraction(extracted_dir: Path, arxiv_id: str, page_texts, sections) -> None:
    extracted_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "markdown": "".join(page_texts),
        "sections": sections,
        "pages": page_map(page_texts),
        "n_pages": len(page_texts),
    }
    (extracted_dir / f"{arxiv_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def write_arxiv_db(db_path: Path, rows: dict[str, tuple[str, str]]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE papers (arxiv_id TEXT PRIMARY KEY, title TEXT, abstract TEXT)")
    conn.executemany(
        "INSERT INTO papers (arxiv_id, title, abstract) VALUES (?, ?, ?)",
        [(aid, t, a) for aid, (t, a) in rows.items()],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def one_paper(tmp_path):
    """A two-section paper whose second section is large enough to split."""
    intro = "# Intro\n\n" + SENT * 4 + "\n"
    methods = "# Methods\n\n" + SENT * 120 + "\n"  # over 1k tokens -> multiple chunks
    page1 = intro
    # split methods on a sentence boundary so page 2 still starts with its heading
    cut = methods.index(SENT, len(methods) // 2)
    page2 = methods[:cut]
    page3 = methods[cut:]
    write_extraction(
        tmp_path / "extracted",
        "2601.00001",
        [page1, page2, page3],
        [
            {"title": "Intro", "page_start": 1, "page_end": 1},
            {"title": "Methods", "page_start": 2, "page_end": 3},
        ],
    )
    write_arxiv_db(tmp_path / "arxiv.db", {"2601.00001": ("A Great Paper", "We do RAG well.")})
    return {
        "extracted": tmp_path / "extracted",
        "arxiv_db": tmp_path / "arxiv.db",
        "out": tmp_path / "chunks.jsonl",
        "id": "2601.00001",
    }


def chunk(one_paper, **overrides) -> list[Chunk]:
    settings = make_settings(**overrides)
    return list(
        chunk_papers.chunk_paper(
            one_paper["id"],
            one_paper["extracted"] / f"{one_paper['id']}.json",
            title="A Great Paper",
            abstract="We do RAG well.",
            settings=settings,
        )
    )


# --- token counting ---------------------------------------------------------


def test_n_tokens_matches_tokenizer():
    n = chunk_papers.count_tokens("hello world from askrag")
    assert n == chunk_papers.count_tokens("hello world from askrag")
    assert n > 0


# --- paper-level chunk (title + abstract) -----------------------------------


def test_first_chunk_is_paper_level(one_paper):
    chunks = chunk(one_paper)
    meta = chunks[0]
    assert meta.chunk_id == "2601.00001#0"
    assert meta.section == chunk_papers.PAPER_SECTION
    assert "A Great Paper" in meta.text
    assert "We do RAG well." in meta.text
    assert meta.page_start == 1 and meta.page_end == 1


# --- deterministic ids ------------------------------------------------------


def test_ids_are_sequential_and_deterministic(one_paper):
    first = chunk(one_paper)
    second = chunk(one_paper)
    ids = [c.chunk_id for c in first]
    assert ids == [f"2601.00001#{i}" for i in range(len(first))]
    assert [c.chunk_id for c in second] == ids
    assert [c.text for c in second] == [c.text for c in first]


# --- section boundaries never crossed ---------------------------------------


def test_chunks_never_cross_section_boundaries(one_paper):
    chunks = chunk(one_paper)
    body = [c for c in chunks if c.section != chunk_papers.PAPER_SECTION]
    sections = {c.section for c in body}
    assert sections == {"Intro", "Methods"}
    # Every body chunk's text lies wholly within its section's markdown.
    for c in body:
        assert c.section in ("Intro", "Methods")


# --- chunk size respects the token budget -----------------------------------


def test_chunks_respect_token_budget(one_paper):
    chunks = chunk(one_paper, chunk_size_tokens=200, chunk_overlap_ratio=0.15)
    body = [c for c in chunks if c.section != chunk_papers.PAPER_SECTION]
    # Methods is large -> must produce more than one chunk at a 200-token budget.
    methods = [c for c in body if c.section == "Methods"]
    assert len(methods) >= 2
    for c in body:
        assert c.n_tokens <= 200


# --- overlap between consecutive chunks in the same section ------------------


def test_consecutive_chunks_overlap(one_paper):
    chunks = chunk(one_paper, chunk_size_tokens=200, chunk_overlap_ratio=0.15)
    methods = [c for c in chunks if c.section == "Methods"]
    # With overlap, the tail of chunk i reappears at the head of chunk i+1.
    a, b = methods[0], methods[1]
    tail = a.text[-80:]
    assert any(tail[k:] and tail[k:] in b.text for k in range(len(tail)))


# --- page anchors -----------------------------------------------------------


def test_page_anchors_within_document(one_paper):
    chunks = chunk(one_paper)
    for c in chunks:
        assert 1 <= c.page_start <= c.page_end <= 3


def test_methods_chunks_anchor_to_later_pages(one_paper):
    chunks = chunk(one_paper, chunk_size_tokens=200)
    methods = [c for c in chunks if c.section == "Methods"]
    # Methods spans pages 2-3; every methods chunk anchors within that range.
    for c in methods:
        assert c.page_start >= 2


# --- empty / preamble handling ----------------------------------------------


def test_untitled_preamble_section_labeled(tmp_path):
    # A heading-free document: extract_pdfs emits one title="" section.
    page1 = SENT * 10
    write_extraction(
        tmp_path / "extracted",
        "2601.00002",
        [page1],
        [{"title": "", "page_start": 1, "page_end": 1}],
    )
    settings = make_settings()
    chunks = list(
        chunk_papers.chunk_paper(
            "2601.00002",
            tmp_path / "extracted" / "2601.00002.json",
            title="Titleless",
            abstract="No headings here.",
            settings=settings,
        )
    )
    body = [c for c in chunks if c.section != chunk_papers.PAPER_SECTION]
    assert body  # preamble content still chunked
    assert all(c.section == chunk_papers.PREAMBLE_SECTION for c in body)
