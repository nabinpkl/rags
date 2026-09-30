"""tool: drive_ui — enum-validated UI actions, server-checked against corpus.db
(§5/§6).

Accepts only the three named actions (`open_paper`, `goto_page`,
`set_filters`), each with its own closed args shape — never a free-form URL
or HTML string (§6: an injected agent has nothing to inject *into*). Every
reference an action carries (paper id, page number, category) is checked
against corpus.db before the tool returns, so a hallucinated or injected
target never reaches the frontend looking like a real one.

`DriveUiArgs` is a `RootModel` over a `Field(discriminator="action")` union:
pydantic picks the matching per-action model from the `action` field alone,
so each action's JSON schema states exactly its own required/forbidden
fields (an `open_paper` call can't also carry `page`) instead of one
loosely-optional mega-schema.
"""

import sqlite3
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from askrag import db
from askrag.facets import INDEXED_PREDICATE


class DriveUiError(Exception):
    """The action's target (paper id, page, category) does not exist (§5)."""


class _DriveUiAction(BaseModel):
    """Shared by the three action shapes: the registry's uniform fence seam
    (§5/§6, 2026-07-06 checkpoint finding 2) — `model_dump()` is already a
    plain dict, so this just names that as the tool-result contract."""

    def to_model_payload(self) -> dict[str, Any]:
        return self.model_dump()


class OpenPaperArgs(_DriveUiAction):
    model_config = ConfigDict(extra="forbid")

    action: Literal["open_paper"] = "open_paper"
    paper_id: str = Field(min_length=1)


class GotoPageArgs(_DriveUiAction):
    model_config = ConfigDict(extra="forbid")

    action: Literal["goto_page"] = "goto_page"
    paper_id: str = Field(min_length=1)
    page: int = Field(ge=1)


class SetFiltersArgs(_DriveUiAction):
    model_config = ConfigDict(extra="forbid")

    action: Literal["set_filters"] = "set_filters"
    category: str | None = None
    year_min: int | None = None
    year_max: int | None = None


_ActionUnion = Annotated[
    OpenPaperArgs | GotoPageArgs | SetFiltersArgs, Field(discriminator="action")
]


class DriveUiArgs(RootModel[_ActionUnion]):
    """Model-facing input: validates + dispatches on `action` alone."""


# Both checks are scoped to the indexed set (D16): the agent may only steer the
# reader to papers it can read, and only to categories that leave the list it
# is steering non-empty.
def _require_paper_exists(conn: sqlite3.Connection, paper_id: str) -> None:
    row = conn.execute(
        f"SELECT 1 FROM papers WHERE arxiv_id = ? AND {INDEXED_PREDICATE}", (paper_id,)
    ).fetchone()
    if row is None:
        raise DriveUiError(f"no indexed paper with id {paper_id!r}")


def _require_page_exists(conn: sqlite3.Connection, paper_id: str, page: int) -> None:
    row = conn.execute(
        "SELECT MAX(page_end) FROM chunks WHERE paper_id = ?", (paper_id,)
    ).fetchone()
    max_page = row[0] if row is not None else None
    if max_page is None or page > max_page:
        raise DriveUiError(f"paper {paper_id!r} has no page {page} (last page: {max_page})")


def _require_category_exists(conn: sqlite3.Connection, category: str) -> None:
    row = conn.execute(
        f"SELECT 1 FROM papers WHERE primary_category = ? AND {INDEXED_PREDICATE} LIMIT 1",
        (category,),
    ).fetchone()
    if row is None:
        raise DriveUiError(f"no indexed paper has category {category!r}")


def run(
    args: DriveUiArgs,
    *,
    corpus_db_path: Path | None = None,
) -> OpenPaperArgs | GotoPageArgs | SetFiltersArgs:
    """Validate the action's target against corpus.db and return it unchanged
    (already the exact per-action shape the frontend forwards, §4c)."""
    action = args.root
    conn = db.connect_corpus(corpus_db_path)
    try:
        if isinstance(action, OpenPaperArgs):
            _require_paper_exists(conn, action.paper_id)
        elif isinstance(action, GotoPageArgs):
            _require_paper_exists(conn, action.paper_id)
            _require_page_exists(conn, action.paper_id, action.page)
        elif action.category is not None:
            _require_category_exists(conn, action.category)
    finally:
        conn.close()
    return action
