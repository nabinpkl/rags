"""Documents + chunks + vectors -> one source's index pair (D4, D21).

For a source with no schema of its own: the contract tables
(index_schema.create_tables), their FTS, and the per-model Chroma collection,
rebuilt as one artifact so the two stores never drift. arXiv keeps its own
builder (ingest/build_indexes.py) because corpus.db also carries the
catalog; both end in the same `index_schema.check` and `load_collection`.

Drop-and-rebuild: the db is written to a tmp file and renamed, the
collection is deleted and recreated. Every invariant is checked before
anything is written, so a failed build leaves the last good pair in place.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from askrag.retrieval import index_schema
from askrag.retrieval.index_location import IndexLocation
from askrag.retrieval.vector_store import load_collection, vector_metadata


class IndexBuildError(Exception):
    """The inputs violate an index invariant."""


@dataclass(frozen=True)
class IndexDocument:
    doc_id: str
    title: str
    day: int  # YYYYMMDD
    version: str | None = None
    facets: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class IndexChunk:
    chunk_id: str  # "<doc_id>#<seq>"
    doc_id: str
    section: str
    pos_start: int
    pos_end: int
    text: str
    n_tokens: int


def _validate(
    documents: Sequence[IndexDocument],
    chunks: Sequence[IndexChunk],
    vector_ids: Sequence[str],
) -> None:
    doc_ids = {d.doc_id for d in documents}
    if len(doc_ids) != len(documents):
        raise IndexBuildError("two documents share a doc_id")
    orphans = sorted({c.doc_id for c in chunks} - doc_ids)
    if orphans:
        raise IndexBuildError(
            f"{len(orphans)} chunk doc_id(s) have no document (first: {orphans[0]})"
        )
    bad_ids = [c.chunk_id for c in chunks if not c.chunk_id.startswith(f"{c.doc_id}#")]
    if bad_ids:
        raise IndexBuildError(f"chunk id {bad_ids[0]!r} is not <doc_id>#<seq>")
    chunk_ids = [c.chunk_id for c in chunks]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise IndexBuildError("two chunks share a chunk_id")
    if sorted(vector_ids) != sorted(chunk_ids):
        missing = sorted(set(chunk_ids) - set(vector_ids))
        extra = sorted(set(vector_ids) - set(chunk_ids))
        raise IndexBuildError(
            f"vectors and chunks differ: {len(missing)} chunk(s) without a vector, "
            f"{len(extra)} vector(s) without a chunk; re-run the embed step"
        )


def build_index(
    location: IndexLocation,
    documents: Sequence[IndexDocument],
    chunks: Sequence[IndexChunk],
    vector_ids: list[str],
    vectors: list[list[float]],
    *,
    add_batch_size: int,
) -> int:
    """Write the db and the collection; returns the collection's count."""
    _validate(documents, chunks, vector_ids)
    location.db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = location.db_path.with_suffix(location.db_path.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        index_schema.create_tables(conn)
        conn.executemany(
            f"INSERT INTO {index_schema.DOCUMENTS} VALUES (?,?,?,?)",
            [(d.doc_id, d.title, d.day, d.version) for d in documents],
        )
        conn.executemany(
            f"INSERT INTO {index_schema.CHUNKS}"
            " (chunk_id, doc_id, section, pos_start, pos_end, text, n_tokens)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                (c.chunk_id, c.doc_id, c.section, c.pos_start, c.pos_end, c.text, c.n_tokens)
                for c in chunks
            ],
        )
        conn.execute(
            f"INSERT INTO {index_schema.CHUNKS_FTS}(rowid, text)"
            f" SELECT chunk_rowid, text FROM {index_schema.CHUNKS}"
        )
        conn.executemany(
            f"INSERT INTO {index_schema.FACETS} VALUES (?,?,?)",
            [(d.doc_id, key, value) for d in documents for key, value in d.facets],
        )
        conn.commit()
        index_schema.check(conn)
    finally:
        conn.close()
    tmp.replace(location.db_path)

    by_doc = {d.doc_id: d for d in documents}
    doc_of = {c.chunk_id: c.doc_id for c in chunks}
    metadatas = [
        vector_metadata(by_doc[doc_of[i]].doc_id, by_doc[doc_of[i]].day, by_doc[doc_of[i]].facets)
        for i in vector_ids
    ]
    count = load_collection(
        location.chroma_dir, location.collection, vector_ids, vectors, metadatas, add_batch_size
    )
    if count != len(chunks):
        raise IndexBuildError(f"{len(chunks)} chunks but the collection holds {count}")
    return count
