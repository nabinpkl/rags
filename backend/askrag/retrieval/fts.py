"""FTS5/BM25 query construction and escaping: the BM25 leg of D8, any source.

User query text is an injection surface (§6): FTS5 MATCH strings carry
operators (AND/OR/NOT/NEAR), column filters (`col:value`), prefix `*`, and
initial-token `^`. `build_match_query` neutralizes ALL of it by reducing the
input to whitespace-separated terms, each double-quoted (internal quotes
doubled — FTS5 string escaping), so user text can only ever be literal terms.
C0 control characters (U+0000-U+001F) and DEL (U+007F) are stripped from each
term before quoting — sqlite3 raises `OperationalError: unterminated string`
if a raw NUL reaches a double-quoted MATCH term, which would otherwise turn
"worst case zero rows" into a syntax error escaping the quotes meant to
prevent exactly that.

Terms join with OR, not FTS5's implicit AND: natural-language queries should
rank partial matches (BM25 scores multi-term hits higher anyway), not return
zero rows because one word is missing.
"""

import sqlite3

from askrag.retrieval.filters import Filters
from askrag.retrieval.index_schema import CHUNKS, CHUNKS_FTS, DOCUMENTS, FACETS

_CONTROL_CHARS = "".join(chr(c) for c in range(0x20)) + "\x7f"
_CONTROL_TABLE = str.maketrans("", "", _CONTROL_CHARS)


def build_match_query(user_query: str) -> str:
    """Any string -> a safe FTS5 MATCH expression (possibly "" = no query)."""
    terms = user_query.split()
    cleaned = [term.translate(_CONTROL_TABLE) for term in terms]
    quoted = ['"' + term.replace('"', '""') + '"' for term in cleaned if term]
    return " OR ".join(quoted)


def search_bm25(conn: sqlite3.Connection, query: str, k: int, filters: Filters) -> list[str]:
    """Rank-ordered chunk_ids from the FTS5 index; filters push into SQL (D8).

    Reads only the index contract (index_schema.py), so it serves any source.
    Returns ids only: hybrid_search hydrates the fused top-k in one query
    instead of every leg dragging full rows around.
    """
    match = build_match_query(query)
    if not match or filters.empty_scope:
        # An empty scope means "no document is in scope", NOT "no filter":
        # the difference between a landing-page claim that owns no indexed
        # papers returning nothing, and it returning the whole corpus.
        return []
    sql = f"SELECT c.chunk_id FROM {CHUNKS_FTS} f JOIN {CHUNKS} c ON c.chunk_rowid = f.rowid"
    params: list[str | int] = []
    if filters.day_min is not None or filters.day_max is not None:
        sql += f" JOIN {DOCUMENTS} d ON d.doc_id = c.doc_id"
    sql += f" WHERE {CHUNKS_FTS} MATCH ?"
    params.append(match)
    if filters.day_min is not None:
        sql += " AND d.day >= ?"
        params.append(filters.day_min)
    if filters.day_max is not None:
        sql += " AND d.day <= ?"
        params.append(filters.day_max)
    for key, value in filters.facets:
        sql += f" AND c.doc_id IN (SELECT doc_id FROM {FACETS} WHERE key = ? AND value = ?)"
        params.extend((key, value))
    if filters.doc_ids is not None:
        sql += f" AND c.doc_id IN ({','.join('?' * len(filters.doc_ids))})"
        params.extend(filters.doc_ids)
    sql += " ORDER BY rank LIMIT ?"
    params.append(k)
    return [row[0] for row in conn.execute(sql, params).fetchall()]
