"""Tests for askrag.tools.registry — tool schemas validate, unknown names refused."""

import pytest

from askrag.tools import drive_ui, query_metadata, read_paper, search_corpus
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
