"""The index contract every source's SQLite file meets (D21).

Retrieval reads four relations by name and nothing else:

    rag_documents  (doc_id, title, day, version)
    rag_chunks     (chunk_rowid, chunk_id, doc_id, section, pos_start, pos_end,
                    text, n_tokens)
    rag_chunks_fts FTS5 over chunk text, its rowid = rag_chunks.chunk_rowid
    rag_facets     (doc_id, key, value)

`day` is YYYYMMDD. `pos_start`/`pos_end` are source-defined positions inside
a document (PDF pages for arXiv, turn numbers for a transcript), inclusive.
`version` is the document's revision where it has one (arXiv's pinned PDF
version, D9), else NULL. Chunk ids are `<doc_id>#<seq>`.

A new source writes these as tables with `create_tables`. A source with its
own richer schema may expose them as views over it instead (arXiv does, so
its catalog keeps one home); `check` holds both to the same columns.
"""

import sqlite3

DOCUMENTS = "rag_documents"
CHUNKS = "rag_chunks"
CHUNKS_FTS = "rag_chunks_fts"
FACETS = "rag_facets"

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    DOCUMENTS: ("doc_id", "title", "day", "version"),
    CHUNKS: (
        "chunk_rowid",
        "chunk_id",
        "doc_id",
        "section",
        "pos_start",
        "pos_end",
        "text",
        "n_tokens",
    ),
    CHUNKS_FTS: ("text",),
    FACETS: ("doc_id", "key", "value"),
}

# The tokenizer both legs' BM25 numbers were measured with (D8).
FTS_TOKENIZE = "porter unicode61"

_TABLES_DDL = f"""
CREATE TABLE {DOCUMENTS} (
    doc_id  TEXT PRIMARY KEY,
    title   TEXT NOT NULL,
    day     INTEGER NOT NULL,
    version TEXT
);
CREATE TABLE {CHUNKS} (
    chunk_rowid INTEGER PRIMARY KEY,
    chunk_id    TEXT NOT NULL UNIQUE,
    doc_id      TEXT NOT NULL REFERENCES {DOCUMENTS}(doc_id),
    section     TEXT NOT NULL,
    pos_start   INTEGER NOT NULL,
    pos_end     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    n_tokens    INTEGER NOT NULL
);
CREATE INDEX {CHUNKS}_doc ON {CHUNKS}(doc_id);
CREATE VIRTUAL TABLE {CHUNKS_FTS} USING fts5(
    text, content={CHUNKS}, content_rowid=chunk_rowid, tokenize='{FTS_TOKENIZE}'
);
CREATE TABLE {FACETS} (
    doc_id TEXT NOT NULL REFERENCES {DOCUMENTS}(doc_id),
    key    TEXT NOT NULL,
    value  TEXT NOT NULL,
    PRIMARY KEY (doc_id, key, value)
) WITHOUT ROWID;
CREATE INDEX {FACETS}_kv ON {FACETS}(key, value);
"""


class IndexContractError(Exception):
    """An index file lacks a relation or column retrieval reads."""


def create_tables(conn: sqlite3.Connection) -> None:
    """The contract as plain tables, for a source with no schema of its own."""
    conn.executescript(_TABLES_DDL)


def fts_ddl(content_table: str, content_rowid: str) -> str:
    """The FTS table over a source's own chunk table (arXiv's `chunks`)."""
    return (
        f"CREATE VIRTUAL TABLE {CHUNKS_FTS} USING fts5("
        f"text, content={content_table}, content_rowid={content_rowid}, "
        f"tokenize='{FTS_TOKENIZE}')"
    )


def check(conn: sqlite3.Connection) -> None:
    """Raise unless every contract relation exists with its columns."""
    for relation, columns in REQUIRED_COLUMNS.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({relation})")}
        if not have:
            raise IndexContractError(f"index has no {relation}")
        missing = [c for c in columns if c not in have]
        if missing:
            raise IndexContractError(f"{relation} lacks column(s) {', '.join(missing)}")
