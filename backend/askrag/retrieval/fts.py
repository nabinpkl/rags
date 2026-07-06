"""FTS5/BM25 query construction and escaping — the BM25 leg of D8.

User query text is an injection surface (§6): FTS5 MATCH strings carry
operators (AND/OR/NOT/NEAR), column filters (`col:value`), prefix `*`, and
initial-token `^`. `build_match_query` neutralizes ALL of it by reducing the
input to whitespace-separated terms, each double-quoted (internal quotes
doubled — FTS5 string escaping), so user text can only ever be literal terms.

Terms join with OR, not FTS5's implicit AND: natural-language queries should
rank partial matches (BM25 scores multi-term hits higher anyway), not return
zero rows because one word is missing.
"""

import sqlite3


def build_match_query(user_query: str) -> str:
    """Any string -> a safe FTS5 MATCH expression (possibly "" = no query)."""
    terms = user_query.split()
    quoted = ['"' + term.replace('"', '""') + '"' for term in terms]
    return " OR ".join(quoted)


def search_bm25(
    conn: sqlite3.Connection,
    query: str,
    k: int,
    *,
    category: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
) -> list[str]:
    """Rank-ordered chunk_ids from the FTS5 index; filters push into SQL (D8).

    Returns ids only — hybrid_search hydrates the fused top-k in one query
    instead of every leg dragging full rows around.
    """
    match = build_match_query(query)
    if not match:
        return []
    sql = (
        "SELECT c.chunk_id FROM chunks_fts f"
        " JOIN chunks c ON c.rowid = f.rowid"
        " JOIN papers p ON p.arxiv_id = c.paper_id"
        " WHERE chunks_fts MATCH ?"
    )
    params: list[str | int] = [match]
    if category is not None:
        sql += " AND p.primary_category = ?"
        params.append(category)
    if year_min is not None:
        sql += " AND p.year >= ?"
        params.append(year_min)
    if year_max is not None:
        sql += " AND p.year <= ?"
        params.append(year_max)
    sql += " ORDER BY rank LIMIT ?"
    params.append(k)
    return [row[0] for row in conn.execute(sql, params).fetchall()]
