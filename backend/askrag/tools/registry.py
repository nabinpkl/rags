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
from typing import Any, Protocol

from pydantic import BaseModel

from askrag.tools import drive_ui, query_metadata, read_paper, search_corpus


class ToolResult(Protocol):
    """The uniform shape every handler's return value satisfies: one method
    turning it into a plain, JSON-shaped dict. This is the fence seam #23
    consumes — wrap `to_model_payload()`'s output in the fenced, "untrusted
    corpus content" block (§5/§6) once, instead of a per-type switch over
    the four heterogeneous result classes (2026-07-06 checkpoint finding 2)."""

    def to_model_payload(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ToolSpec:
    """One entry in the model-facing tool surface: schema + its handler."""

    name: str
    description: str
    args_model: type[BaseModel]
    # `Callable[[Any], ToolResult]`, not `Callable[[BaseModel], ToolResult]`:
    # each handler below takes its OWN args subclass (SearchCorpusArgs, not
    # bare BaseModel), which a contravariant parameter type would reject
    # here. The return side is `ToolResult`, not `Any` — dispatch() below no
    # longer hands its caller an unfenceable heterogeneous value.
    handler: Callable[..., ToolResult]
    # Whether this tool reads paper content, and must therefore honor a
    # conversation scope. `query_metadata` and `drive_ui` are unscoped: the
    # first returns counts over the already-D16-scoped corpus, the second
    # only moves the UI. Scoping is opt-IN per tool so a new content-reading
    # tool has to state that it read this comment.
    scoped: bool = False

    @property
    def json_schema(self) -> dict[str, Any]:
        """The model-facing schema, in the one shape the Messages API accepts.

        `query_metadata` and `drive_ui` are RootModels over a discriminated
        union, and pydantic emits that as a top-level `oneOf`. The API refuses
        it outright: "input_schema does not support oneOf, allOf, or anyOf at
        the top level". So the union is flattened to one object schema here.

        This does NOT loosen either tool. `dispatch` validates raw_args against
        `args_model` — the union itself — so an op/field combination the union
        forbids is still rejected server-side. The schema is what the model is
        TOLD; the union is what is ACCEPTED, and only the latter is a security
        boundary (§5/§6: enum'd ops, no model-authored SQL, no URLs or HTML).

        Both facts were found by the live smoke, one API error at a time; every
        test scripts the model client, so nothing offline exercises this shape.
        """
        return _anthropic_input_schema(self.args_model.model_json_schema())


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    """Inline every `$ref` against `$defs` so the emitted schema stands alone."""
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return _resolve({k: v for k, v in defs.get(name, {}).items()}, defs)
        return {k: _resolve(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_resolve(v, defs) for v in node]
    return node


def _anthropic_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A pydantic JSON schema as an Anthropic `input_schema`.

    A top-level discriminated union becomes a single object: the union of every
    variant's properties, with only the discriminator required and its enum
    listing the permitted ops. Each optional property names the ops it belongs
    to, so the flattening costs the model guidance, not correctness — the union
    still gates what `dispatch` accepts.
    """
    defs = schema.get("$defs", {})
    branches = schema.get("oneOf") or schema.get("anyOf")
    if not branches:
        flat = _resolve(schema, defs)
        flat.setdefault("type", "object")
        return flat

    key = schema.get("discriminator", {}).get("propertyName", "op")
    properties: dict[str, Any] = {}
    ops: list[str] = []
    owners: dict[str, list[str]] = {}
    for branch in branches:
        resolved = _resolve(branch, defs)
        op = resolved.get("properties", {}).get(key, {}).get("const")
        if op is not None:
            ops.append(op)
        for prop, spec in resolved.get("properties", {}).items():
            if prop == key:
                continue
            properties.setdefault(prop, dict(spec))
            if op is not None:
                owners.setdefault(prop, []).append(op)

    for prop, used_by in owners.items():
        note = f"Used with {key}=" + " or ".join(repr(o) for o in used_by) + "."
        existing = properties[prop].get("description")
        properties[prop]["description"] = f"{existing} {note}".strip() if existing else note

    return {
        "type": "object",
        "description": schema.get("description", ""),
        "properties": {key: {"type": "string", "enum": ops}, **properties},
        "required": [key],
    }


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
        scoped=True,
    ),
    "query_metadata": ToolSpec(
        name="query_metadata",
        description=(
            "Query corpus-wide facts: count_papers (scalar count or a "
            "group-by histogram over category/year/license/venue, with "
            "category/year_min/year_max/has_license filters), paper_facets "
            "(one paper's title/category/year/version/license/venue/"
            "chunk-and-page counts by id), or corpus_stats (paper/chunk "
            "totals, year range, category count)."
        ),
        args_model=query_metadata.QueryMetadataArgs,
        handler=query_metadata.run,
    ),
    "read_paper": ToolSpec(
        name="read_paper",
        description=(
            "Read extracted text from one paper for deep analysis, optionally "
            "restricted to a page range. Returns page-ordered spans up to a "
            "token budget — use this to read a paper more deeply than the "
            "chunks search_corpus returns."
        ),
        args_model=read_paper.ReadPaperArgs,
        handler=read_paper.run,
        scoped=True,
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


def dispatch(
    name: str, raw_args: dict[str, Any], *, scope: tuple[str, ...] | None = None
) -> ToolResult:
    """Validate `raw_args` against the named tool's schema, then call its
    handler. Raises `UnknownToolError` for anything not in `TOOLS` — this
    file never falls back to open dispatch by name.

    `scope` is the conversation's paper-id restriction, resolved server-side
    from a landing-page claim (routes_landing.scope_paper_ids). It reaches
    content-reading tools as a keyword the model cannot author, so no argument
    the model writes can widen it."""
    if name not in TOOLS:
        raise UnknownToolError(f"no such tool: {name!r}")
    spec = TOOLS[name]
    args = spec.args_model.model_validate(raw_args)
    return spec.handler(args, scope=scope) if spec.scoped else spec.handler(args)
