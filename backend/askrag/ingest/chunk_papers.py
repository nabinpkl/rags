"""corpus/extracted/{arxiv_id}.json + arxiv.db -> corpus/chunks.jsonl (D7).

Section-aware, page-anchored chunking. Sections come from the extraction's
markdown heading structure (D6); each section is packed into ~chunk_size_tokens
chunks with ~chunk_overlap_ratio overlap and never crossing a section boundary.
Every paper additionally gets one paper-level chunk (title + abstract) so
coarse retrieval and the explorer's semantic search have a cheap whole-paper
handle (D7).

Chunk record — a FROZEN interface consumed by embed_chunks (#13) and
build_indexes (#14):

    {"chunk_id": "{paper_id}#{seq}",   # seq is a per-paper counter from 0
     "paper_id": str,
     "section": str,                    # heading title, or the sentinels below
     "page_start": int, "page_end": int,  # 1-based, inclusive (PDF #page anchors, D9)
     "text": str,
     "n_tokens": int}                   # counted with config.tokenizer_encoding

Section LABELS come from the extraction's authoritative stored `sections`
list (one source, per D6); char BOUNDARIES come from the same heading regex
extract_pdfs uses (imported, not duplicated). The two are aligned 1:1 by
position — exact because extract_pdfs creates one stored section per heading
match, in order, plus an optional leading preamble. A section runs from its
heading to the next, tiling the document, unlike the extractor's page-range
sections which deliberately share boundary pages. Labels are NOT re-derived by
re-cleaning heading text and matching a filtered title list: a bold heading
that pymupdf4llm splits into a stray ``# ***`` line adds a regex match with an
empty stored title, and index-pairing against non-empty titles would shift
every later label (reviewer round 1, corpus/extracted/2606.08629.json). Page
anchors come from mapping a chunk's char range back through the page map.

Determinism (acceptance): ids are a per-paper sequence over papers processed
in sorted id order; the whole file is rewritten each run, so a re-run over the
same inputs yields byte-identical ids and text.
"""

import argparse
import json
import logging
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import tiktoken

from askrag import telemetry
from askrag.config import Settings, get_settings
from askrag.ingest.extract_pdfs import _HEADING_RE

_log = logging.getLogger("askrag.ingest.chunk_papers")

# Sentinel section labels (protocol facts, not tunables): the paper-level
# chunk and a heading-free document's preamble both need a stable name.
PAPER_SECTION = "__paper__"
PREAMBLE_SECTION = "__preamble__"


@dataclass(frozen=True)
class Chunk:
    """The frozen chunk record; asdict() of this is the JSONL line shape."""

    chunk_id: str
    paper_id: str
    section: str
    page_start: int
    page_end: int
    text: str
    n_tokens: int


@lru_cache(maxsize=4)
def _encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def count_tokens(text: str, encoding: str) -> int:
    # `encoding` is required (no default): the encoding name lives once, in
    # config.tokenizer_encoding, so callers pass it rather than duplicate it.
    return len(encode_corpus_text(text, encoding))


def encode_corpus_text(text: str, encoding: str) -> list[int]:
    """Tokenize paper text, treating control-token spellings as ordinary text.

    tiktoken raises on a literal "<|endofprompt|>" by default, and papers ABOUT
    language models quote those strings — one frontier paper killed a whole
    chunking run this way. `disallowed_special=()` makes them plain characters,
    which is both the correct reading of a paper quoting a token and the safe
    one: corpus text is untrusted (§6), so it must never be able to mint a
    control token in anything downstream.
    """
    return _encoding(encoding).encode(text, disallowed_special=())


@dataclass(frozen=True)
class _SectionSpan:
    """A section's title and its [char_start, char_end) range in the markdown."""

    title: str
    char_start: int
    char_end: int


def _section_spans(markdown: str, sections: list[dict]) -> list[_SectionSpan]:
    """Map the extractor's authoritative section list to char ranges.

    LABELS come from the ONE authoritative source — the extraction's stored
    `sections` list, in order, keeping empty-title entries (extract_pdfs
    creates one section per heading match, plus an optional leading preamble
    for content before the first heading). Char BOUNDARIES come from the same
    heading regex the extractor used; the two are aligned positionally, which
    is exact because both derive from the identical ordered set of matches.

    This is NOT a second label-deriving pass: re-cleaning heading text and
    pairing it against a *filtered* title list drifts when pymupdf4llm splits
    a bold heading into a stray ``# ***`` line (that becomes a title="" stored
    section but an extra regex match), shifting every later label. Taking
    labels from the stored list and asserting the 1:1 alignment removes that
    class of bug (reviewer round 1, corpus/extracted/2606.08629.json).
    """
    heads = [m.start() for m in _HEADING_RE.finditer(markdown)]
    spans: list[_SectionSpan] = []

    # extract_pdfs prepends a stored preamble section ONLY when the first
    # heading is not on page 1; then len(sections) == len(heads) + 1 and
    # sections[0] is that preamble. Otherwise the counts are equal. Decide by
    # count (not by "is there text before the first heading"): a paper whose
    # first heading sits on page 1 after a title/arXiv-header line has leading
    # text but no stored preamble section.
    has_stored_preamble = len(sections) == len(heads) + 1
    aligned = sections[1:] if has_stored_preamble else sections

    # Invariant (extract_pdfs construction): one stored section per heading
    # match after any preamble. A mismatch means the extraction contract
    # changed — raise rather than silently mislabel (D6/D7 move in lockstep).
    if len(aligned) != len(heads):
        raise ValueError(
            f"section/heading mismatch: {len(aligned)} sections vs {len(heads)} "
            "headings — extraction contract changed (see chunk_papers docstring)"
        )

    # Leading content before the first heading still needs page anchors. Label
    # it from the stored preamble when one exists, else the sentinel; text is
    # never silently dropped.
    lead_end = heads[0] if heads else len(markdown)
    if lead_end > 0:
        label = sections[0]["title"] if has_stored_preamble else ""
        spans.append(_SectionSpan(label or PREAMBLE_SECTION, 0, lead_end))

    for i, start in enumerate(heads):
        end = heads[i + 1] if i + 1 < len(heads) else len(markdown)
        title = aligned[i]["title"] or PREAMBLE_SECTION
        spans.append(_SectionSpan(title, start, end))
    return spans


def _page_for_offset(pages: list[dict], offset: int) -> int:
    """1-based page whose [char_start, char_end) contains offset.

    char_end is exclusive and the pages tile the markdown, so the last page
    owns the final boundary offset.
    """
    for page in pages:
        if page["char_start"] <= offset < page["char_end"]:
            return int(page["page"])
    return int(pages[-1]["page"])


def _windows(n_tokens: int, size: int, overlap_ratio: float) -> Iterator[tuple[int, int]]:
    """Token-index windows [i, j) of at most `size`, stepping by size-overlap."""
    step = max(1, size - round(size * overlap_ratio))
    i = 0
    while i < n_tokens:
        yield i, min(i + size, n_tokens)
        if i + size >= n_tokens:
            return
        i += step


def _chunk_section(
    span: _SectionSpan,
    markdown: str,
    pages: list[dict],
    enc: tiktoken.Encoding,
    size: int,
    overlap_ratio: float,
) -> Iterator[tuple[str, str, int, int, int]]:
    """Yield (section, text, page_start, page_end, n_tokens) for one section."""
    section_text = markdown[span.char_start : span.char_end]
    if not section_text.strip():
        return
    tokens = enc.encode(section_text, disallowed_special=())
    for i, j in _windows(len(tokens), size, overlap_ratio):
        # Prefix decode is exact for cl100k, so token boundaries map to char
        # offsets within the section; shift by char_start for absolute offsets.
        rel_start = len(enc.decode(tokens[:i]))
        rel_end = len(enc.decode(tokens[:j]))
        text = section_text[rel_start:rel_end]
        if not text.strip():
            continue
        abs_start = span.char_start + rel_start
        abs_end = span.char_start + rel_end
        page_start = _page_for_offset(pages, abs_start)
        page_end = _page_for_offset(pages, max(abs_start, abs_end - 1))
        yield span.title, text, page_start, page_end, j - i


def chunk_paper(
    paper_id: str,
    extraction_path: Path,
    title: str,
    abstract: str,
    settings: Settings,
) -> Iterator[Chunk]:
    """Yield the paper-level chunk then every section chunk, seq from 0."""
    payload = json.loads(extraction_path.read_text(encoding="utf-8"))
    markdown: str = payload["markdown"]
    pages: list[dict] = payload["pages"]
    sections: list[dict] = payload["sections"]

    enc = _encoding(settings.tokenizer_encoding)
    seq = 0

    meta_text = f"{title}\n\n{abstract}".strip()
    yield Chunk(
        chunk_id=f"{paper_id}#{seq}",
        paper_id=paper_id,
        section=PAPER_SECTION,
        page_start=1,
        page_end=1,
        text=meta_text,
        n_tokens=len(enc.encode(meta_text, disallowed_special=())),
    )
    seq += 1

    for span in _section_spans(markdown, sections):
        for section, text, page_start, page_end, n_tokens in _chunk_section(
            span, markdown, pages, enc, settings.chunk_size_tokens, settings.chunk_overlap_ratio
        ):
            yield Chunk(
                chunk_id=f"{paper_id}#{seq}",
                paper_id=paper_id,
                section=section,
                page_start=page_start,
                page_end=page_end,
                text=text,
                n_tokens=n_tokens,
            )
            seq += 1


def _load_metadata(arxiv_db_path: Path) -> dict[str, tuple[str, str]]:
    """arxiv_id -> (title, abstract) for every paper in the collector's index."""
    # Read-only: the collector owns arxiv.db; ingest never writes it.
    uri = f"{arxiv_db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute("SELECT arxiv_id, title, abstract FROM papers").fetchall()
    return {aid: (title or "", abstract or "") for aid, title, abstract in rows}


def run(extracted_dir: Path, arxiv_db_path: Path, chunks_path: Path, settings: Settings) -> int:
    """Chunk every extraction JSON into chunks_path (JSONL). Returns chunk count."""
    metadata = _load_metadata(arxiv_db_path)
    extraction_files = sorted(extracted_dir.glob("*.json"))

    tracer = telemetry.get_tracer("askrag.ingest.chunk_papers")
    per_paper: list[int] = []
    total = 0
    missing_meta = 0
    tmp = chunks_path.with_suffix(chunks_path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)

    with tracer.start_as_current_span("askrag.ingest.chunk") as run_span:
        with tmp.open("w", encoding="utf-8") as out:
            for path in extraction_files:
                paper_id = path.stem
                title, abstract = metadata.get(paper_id, ("", ""))
                if paper_id not in metadata:
                    missing_meta += 1
                    _log.warning(
                        "no arxiv.db metadata for %s; paper-level chunk has empty title/abstract",
                        paper_id,
                        extra={"askrag_extra": {"askrag.arxiv_id": paper_id}},
                    )
                count = 0
                for chunk in chunk_paper(paper_id, path, title, abstract, settings):
                    out.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
                    count += 1
                per_paper.append(count)
                total += count
        run_span.set_attribute("askrag.papers", len(extraction_files))
        run_span.set_attribute("askrag.chunks", total)
        run_span.set_attribute("askrag.missing_metadata", missing_meta)

    tmp.replace(chunks_path)
    _print_distribution(len(extraction_files), per_paper, total, missing_meta, chunks_path)
    return total


def _print_distribution(
    papers: int, per_paper: list[int], total: int, missing_meta: int, chunks_path: Path
) -> None:
    if not papers:
        print(
            f"chunk_papers: no extraction JSON found; nothing written to {chunks_path}",
            flush=True,
        )
        return
    ordered = sorted(per_paper)
    mean = total / papers
    median = ordered[len(ordered) // 2]
    print(
        f"chunk_papers: {papers} papers -> {total} chunks "
        f"(mean {mean:.1f}, median {median}, min {ordered[0]}, max {ordered[-1]} per paper)",
        flush=True,
    )
    if missing_meta:
        print(
            f"  {missing_meta} papers had no arxiv.db metadata (empty title/abstract)",
            flush=True,
        )
    print(f"  chunks: {chunks_path}", flush=True)


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    telemetry.init(settings)  # entrypoint owns telemetry setup (D15)
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    try:
        run(
            extracted_dir=settings.extracted_dir,
            arxiv_db_path=settings.arxiv_db_path,
            chunks_path=settings.chunks_jsonl_path,
            settings=settings,
        )
    finally:
        telemetry.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
