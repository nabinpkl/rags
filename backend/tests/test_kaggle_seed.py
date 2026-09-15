"""kaggle_seed: targeted streaming lookup, and the two date traps in the catalog."""

import json
import zipfile
from pathlib import Path

from askrag.ingest import kaggle_seed

_RECORDS = [
    {
        "id": "0704.0001",
        "title": "Calculation of prompt diphoton production\n  cross sections",
        "authors": "C. Bal\\'azs, E. L. Berger",
        "categories": "hep-ph",
        "license": None,
        "versions": [
            {"version": "v1", "created": "Mon, 2 Apr 2007 19:18:42 GMT"},
            {"version": "v2", "created": "Tue, 24 Jul 2007 20:10:27 GMT"},
        ],
    },
    {
        "id": "2505.09388",
        "title": "Qwen3 Technical Report",
        "authors": "An Yang and Anfeng Li",
        "categories": "cs.CL cs.AI",
        "license": "http://creativecommons.org/licenses/by/4.0/",
        "versions": [{"version": "v1", "created": "Wed, 14 May 2025 09:00:00 GMT"}],
    },
    {
        "id": "2402.03300",
        "title": "DeepSeekMath",
        "authors": "Zhihong Shao",
        "categories": "cs.CL",
        "license": None,
        "versions": [{"version": "v1", "created": "Mon, 5 Feb 2024 09:00:00 GMT"}],
    },
]


def _seed_zip(tmp_path: Path) -> Path:
    path = tmp_path / "archive.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            kaggle_seed.SEED_MEMBER,
            "".join(json.dumps(record) + "\n" for record in _RECORDS),
        )
    return path


def test_iter_records_returns_only_wanted_ids(tmp_path: Path) -> None:
    found = list(kaggle_seed.iter_records(_seed_zip(tmp_path), {"2505.09388", "2402.03300"}))
    assert {record["id"] for record in found} == {"2505.09388", "2402.03300"}


def test_iter_records_with_no_wanted_ids_never_opens_the_zip(tmp_path: Path) -> None:
    """An empty want-set must not cost a pass over 5.5 GB — or even a file open."""
    assert list(kaggle_seed.iter_records(tmp_path / "does-not-exist.zip", set())) == []


def test_iter_records_ignores_ids_the_catalog_lacks(tmp_path: Path) -> None:
    found = list(kaggle_seed.iter_records(_seed_zip(tmp_path), {"2505.09388", "9999.99999"}))
    assert [record["id"] for record in found] == ["2505.09388"]


def test_first_version_year_is_v1_not_the_latest_revision() -> None:
    """The trap: OAI `<created>` dates the LATEST version.

    0704.0001 was submitted in 2007 and revised in 2007 here; a paper revised
    years later would be misplaced by the whole gap if the last version won.
    """
    assert kaggle_seed.first_version_year(_RECORDS[0]) == 2007
    assert kaggle_seed.first_version_year(_RECORDS[1]) == 2025


def test_first_version_year_of_a_versionless_record_is_none() -> None:
    assert kaggle_seed.first_version_year({"id": "x", "versions": []}) is None
    assert kaggle_seed.first_version_year({"id": "x"}) is None


def test_latest_version_is_the_pin_for_arxiv_links() -> None:
    """D9 pins PDF URLs to a version; the newest is what a reader should land on."""
    assert kaggle_seed.latest_version(_RECORDS[0]) == "v2"
    assert kaggle_seed.latest_version(_RECORDS[1]) == "v1"
    assert kaggle_seed.latest_version({"id": "x", "versions": []}) is None


# --- the catalog census: the denominator the landing page had no way to state -


def test_count_cs_papers_by_id_month_counts_cs_primary_per_month(tmp_path: Path) -> None:
    counts = kaggle_seed.count_cs_papers_by_id_month(_seed_zip(tmp_path))

    # hep-ph primary is not ours to count; the two cs records sit in
    # different id-months.
    assert counts == {"2505": 1, "2402": 1}


def test_count_cs_papers_by_id_month_counts_a_cross_listed_paper_by_its_primary(
    tmp_path: Path,
) -> None:
    """The collector filtered on the categories string's prefix, so the FIRST
    category decides. A denominator built on any-category membership would
    exceed the numerator it is divided into."""
    path = tmp_path / "archive.zip"
    records = [
        {"id": "2607.00001", "categories": "cs.CL stat.ML"},  # ours
        {"id": "2607.00002", "categories": "stat.ML cs.CL"},  # not ours
        {"id": "cs/0701001", "categories": "cs.CL"},  # old-style: no id-month
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(kaggle_seed.SEED_MEMBER, "".join(json.dumps(r) + "\n" for r in records))

    assert kaggle_seed.count_cs_papers_by_id_month(path) == {"2607": 1}
