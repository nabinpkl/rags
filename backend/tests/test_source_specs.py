"""Tests for askrag.sources.source_specs."""

import pytest

from askrag.config import Settings
from askrag.sources.source_specs import SOURCES


@pytest.fixture(autouse=True)
def _no_local_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def test_every_source_names_itself_and_an_index():
    settings = Settings()
    for name, spec in SOURCES.items():
        assert spec.name == name
        assert (
            spec.index(settings).collection == spec.search_settings(settings).embedding_model_slug
        )


def test_the_sources_keep_separate_index_files():
    settings = Settings()
    paths = {spec.index(settings).db_path for spec in SOURCES.values()}
    assert len(paths) == len(SOURCES)
