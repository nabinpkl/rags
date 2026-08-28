"""resolve_cited_works: catalog metadata for works we cite but do not hold."""

import json
import zipfile
from pathlib import Path

from askrag.ingest import kaggle_seed
from askrag.ingest.resolve_cited_works import read_cited_works, run

_RECORDS = [
    {
        "id": "2505.09388",
        "title": "Qwen3 Technical\n  Report",
        "authors": "An Yang,\n  Anfeng Li",
        "categories": "cs.CL cs.AI",
        "versions": [
            {"version": "v1", "created": "Wed, 14 May 2025 09:00:00 GMT"},
            {"version": "v2", "created": "Thu, 15 May 2025 09:00:00 GMT"},
        ],
    },
    {
        "id": "1707.06347",
        "title": "Proximal Policy Optimization Algorithms",
        "authors": "John Schulman",
        "categories": "cs.LG",
        "versions": [{"version": "v2", "created": "Thu, 20 Jul 2017 09:00:00 GMT"}],
    },
]


def _fixtures(tmp_path: Path, edges: list[tuple[str, str]]) -> tuple[Path, Path, Path]:
    citations = tmp_path / "citations.tsv"
    citations.write_text("".join(f"{a}\t{b}\n" for a, b in edges), encoding="utf-8")
    seed = tmp_path / "archive.zip"
    with zipfile.ZipFile(seed, "w") as archive:
        archive.writestr(
            kaggle_seed.SEED_MEMBER,
            "".join(json.dumps(record) + "\n" for record in _RECORDS),
        )
    return citations, seed, tmp_path / "cited_works.jsonl"


def test_resolves_metadata_for_cited_works(tmp_path: Path) -> None:
    citations, seed, out = _fixtures(
        tmp_path, [("2608.00001", "2505.09388"), ("2608.00002", "1707.06347")]
    )

    stats = run(citations, seed, out)

    assert (stats.distinct_cited, stats.resolved, stats.unresolved) == (2, 2, 0)
    rows = {row.arxiv_id: row for row in read_cited_works(out)}
    qwen = rows["2505.09388"]
    # Catalog titles and author lists wrap across lines; the wrapping is not
    # part of the title and must not reach the page.
    assert qwen.title == "Qwen3 Technical Report"
    assert qwen.authors == "An Yang, Anfeng Li"
    assert qwen.primary_category == "cs.CL"
    assert qwen.year == 2025
    assert qwen.version == "v2"
    assert qwen.resolved


def test_unresolvable_ids_are_kept_with_null_metadata(tmp_path: Path) -> None:
    """A citation to a work the catalog lacks is still a citation.

    Dropping the row would quietly shrink every count the landing page derives
    from the edge list, which is the one failure mode a reader cannot detect.
    """
    citations, seed, out = _fixtures(
        tmp_path, [("2608.00001", "2505.09388"), ("2608.00001", "9999.99999")]
    )

    stats = run(citations, seed, out)

    assert (stats.distinct_cited, stats.resolved, stats.unresolved) == (2, 1, 1)
    rows = {row.arxiv_id: row for row in read_cited_works(out)}
    assert set(rows) == {"2505.09388", "9999.99999"}
    assert rows["9999.99999"].title is None
    assert not rows["9999.99999"].resolved


def test_each_cited_work_appears_once(tmp_path: Path) -> None:
    """Many citers, one row: the table is keyed by work, not by edge."""
    citations, seed, out = _fixtures(
        tmp_path,
        [("2608.00001", "2505.09388"), ("2608.00002", "2505.09388")],
    )

    stats = run(citations, seed, out)

    assert stats.distinct_cited == 1
    assert [row.arxiv_id for row in read_cited_works(out)] == ["2505.09388"]


def test_output_is_sorted_and_leaves_no_scratch_file(tmp_path: Path) -> None:
    citations, seed, out = _fixtures(
        tmp_path, [("2608.00001", "2505.09388"), ("2608.00001", "1707.06347")]
    )

    run(citations, seed, out)

    ids = [row.arxiv_id for row in read_cited_works(out)]
    assert ids == sorted(ids)
    assert not out.with_suffix(".jsonl.tmp").exists()
