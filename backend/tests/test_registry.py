"""Tests for askrag.tools.registry — tool schemas validate, unknown names refused."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from askrag.tools import drive_ui, query_metadata, read_paper, registry, search_corpus
from askrag.tools.registry import TOOLS, UnknownToolError, dispatch


def test_registry_is_a_literal_dict_of_the_four_tools():
    # §5's whole tool surface, in one file, one read (§4d: no decorator scan).
    assert set(TOOLS) == {"search_corpus", "query_metadata", "read_paper", "drive_ui"}


@pytest.mark.parametrize(
    ("name", "args_model"),
    [
        ("search_corpus", search_corpus.SearchCorpusArgs),
        ("query_metadata", query_metadata.QueryMetadataArgs),
        ("read_paper", read_paper.ReadPaperArgs),
        ("drive_ui", drive_ui.DriveUiArgs),
    ],
)
def test_each_tool_wires_its_own_args_model_and_handler(name, args_model):
    spec = TOOLS[name]
    assert spec.name == name
    assert spec.args_model is args_model
    assert spec.description  # a model-facing tool needs a non-empty description


@pytest.mark.parametrize("name", list(TOOLS))
def test_json_schema_is_a_valid_object_schema(name):
    schema = TOOLS[name].json_schema
    assert isinstance(schema, dict)
    # drive_ui's schema is a discriminated oneOf, not a single "object" type;
    # everything else is a plain object schema.
    assert schema.get("type") == "object" or "oneOf" in schema


def test_dispatch_validates_args_before_calling_the_handler():
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError, exact type not the point
        dispatch("search_corpus", {"k": 5})  # missing required 'query'


def test_dispatch_rejects_unknown_tool_names():
    with pytest.raises(UnknownToolError, match="hack_the_mainframe"):
        dispatch("hack_the_mainframe", {})


def test_dispatch_never_falls_back_to_open_name_lookup(monkeypatch):
    # A tool name that happens to match a Python builtin or module attribute
    # must still be refused — dispatch only ever looks in TOOLS.
    with pytest.raises(UnknownToolError):
        dispatch("run", {})
    with pytest.raises(UnknownToolError):
        dispatch("__init__", {})


def test_only_content_reading_tools_are_scoped():
    """Scoping is opt-in per tool, so a new content tool must state its choice.

    query_metadata returns counts over the already-D16-scoped corpus and
    drive_ui only moves the UI; neither reads paper text.
    """
    scoped = {name for name, spec in registry.TOOLS.items() if spec.scoped}

    assert scoped == {"search_corpus", "read_paper"}


def test_dispatch_forwards_the_scope_to_scoped_tools_only(monkeypatch):
    seen: dict[str, object] = {}

    class Result:
        def to_model_payload(self):
            return {}

    def scoped_handler(args, *, scope=None):
        seen["scoped"] = scope
        return Result()

    def plain_handler(args):
        seen["plain"] = "called"
        return Result()

    monkeypatch.setitem(
        registry.TOOLS,
        "search_corpus",
        replace(registry.TOOLS["search_corpus"], handler=scoped_handler),
    )
    monkeypatch.setitem(
        registry.TOOLS,
        "drive_ui",
        replace(registry.TOOLS["drive_ui"], handler=plain_handler),
    )

    registry.dispatch("search_corpus", {"query": "x"}, scope=("2401.00001",))
    registry.dispatch("drive_ui", {"action": "open_paper", "paper_id": "2401.00001"})

    assert seen == {"scoped": ("2401.00001",), "plain": "called"}


def test_every_tool_schema_is_a_valid_anthropic_input_schema():
    """The Messages API rejects `input_schema` without a top-level `type`.

    Pydantic emits discriminated unions (query_metadata, drive_ui) as a bare
    `oneOf`, so the live API returned
    `tools.1.custom.input_schema.type: Field required` on the very first real
    request. Every test scripts the model client, so only a live turn could
    surface it — this test is the standing replacement for that turn.
    """
    for spec in registry.TOOLS.values():
        schema = spec.json_schema
        assert schema.get("type") == "object", f"{spec.name} has no top-level type"


def test_the_union_still_gates_what_dispatch_accepts():
    """The advertised schema is flattened; the ACCEPTED shape is not.

    json_schema() no longer carries `oneOf` — the Messages API refuses it at
    the top level. The security boundary is `args_model`, which dispatch
    validates against, so it must stay a discriminated union (§5/§6: enum'd
    ops, no model-authored SQL, no URLs or HTML).
    """
    for name in ("query_metadata", "drive_ui"):
        spec = registry.TOOLS[name]
        assert "oneOf" in spec.args_model.model_json_schema(), f"{name} lost its union"
        # ...and the flattened advertisement is what the API will accept.
        assert "oneOf" not in spec.json_schema
        assert spec.json_schema["type"] == "object"


def test_an_op_field_combination_the_union_forbids_is_still_rejected():
    """Flattening the advertisement must not widen what runs.

    The flat schema lets a model *ask* for corpus_stats with a paper_id; the
    union must still refuse it, because that is where enforcement lives.
    """
    with pytest.raises(ValidationError):
        dispatch("query_metadata", {"op": "corpus_stats", "paper_id": "2505.09388"})


def test_an_op_outside_the_enum_is_rejected():
    with pytest.raises(ValidationError):
        dispatch("query_metadata", {"op": "run_sql", "sql": "SELECT 1"})
