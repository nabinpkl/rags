"""Tool JSON schemas sent to the model + name -> handler dispatch (§5).

A LITERAL DICT, not a decorator scan (§4d: no metaprogramming, no dynamic
imports) — an agent reading this one file sees the entire tool surface: every
name the model can call, its schema, and exactly which function runs. Nothing
here execs, imports by string, or walks a package for `@tool`-decorated
functions.

Read-only by construction (§6): every handler below only ever opens
`db.connect_corpus`, a `mode=ro` SQLite connection (§4c) — the boundary is
enforced where those connections are created, not by convention here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from askrag.tools import drive_ui, query_metadata, read_paper, search_corpus


@dataclass(frozen=True)
class ToolSpec:
    """One entry in the model-facing tool surface: schema + its handler."""

    name: str
    description: str
    args_model: type[BaseModel]
    # `Callable[[Any], Any]`, not `Callable[[BaseModel], Any]`: each handler
    # below takes its OWN args subclass (SearchCorpusArgs, not bare
    # BaseModel), which a contravariant parameter type would reject here.
    handler: Callable[[Any], Any]

    @property
    def json_schema(self) -> dict[str, Any]:
        return self.args_model.model_json_schema()


class UnknownToolError(Exception):
    """The model asked for a tool name that isn't in the registry (§5)."""


TOOLS: dict[str, ToolSpec] = {
    "search_corpus": ToolSpec(
        name="search_corpus",
        description=(
            "Hybrid keyword+vector search over the arXiv CS corpus. Returns "
            "the top-k matching chunks with paper id, section, page range, "
            "and text — use this to find passages relevant to a question."
        ),
        args_model=search_corpus.SearchCorpusArgs,
        handler=search_corpus.run,
    ),
    "query_metadata": ToolSpec(
        name="query_metadata",
        description=(
            "Run a single read-only SELECT statement over corpus.db's "
            "`papers` and `chunks` tables (e.g. counting papers per category, "
            "listing papers by year). No writes, PRAGMAs, or multi-statement "
            "SQL are accepted."
        ),
        args_model=query_metadata.QueryMetadataArgs,
        handler=query_metadata.run,
    ),
    "read_paper": ToolSpec(
        name="read_paper",
        description=(
            "Read extracted text spans from one paper, optionally restricted "
            "to a page range. Returns a small, word-capped set of spans, "
            "never the paper's full text."
        ),
        args_model=read_paper.ReadPaperArgs,
        handler=read_paper.run,
    ),
    "drive_ui": ToolSpec(
        name="drive_ui",
        description=(
            "Drive the explorer UI: open a paper, jump to a page, or set "
            "search filters. Every target is validated against corpus.db "
            "before the action is forwarded."
        ),
        args_model=drive_ui.DriveUiArgs,
        handler=drive_ui.run,
    ),
}


def dispatch(name: str, raw_args: dict[str, Any]) -> Any:
    """Validate `raw_args` against the named tool's schema, then call its
    handler. Raises `UnknownToolError` for anything not in `TOOLS` — this
    file never falls back to open dispatch by name."""
    if name not in TOOLS:
        raise UnknownToolError(f"no such tool: {name!r}")
    spec = TOOLS[name]
    args = spec.args_model.model_validate(raw_args)
    return spec.handler(args)
