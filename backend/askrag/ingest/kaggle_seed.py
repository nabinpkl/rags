"""Streaming reader for the Kaggle arXiv metadata snapshot (`corpus/archive.zip`).

Two ingest stages read this catalog for different fields — build_indexes for
per-paper license (§6b), resolve_cited_works for the title/authors/category of
works we cite but do not hold. The member name and the streaming discipline are
one fact, so they live in one place rather than being restated per consumer.

The snapshot is ~1.8 GB compressed and 5.5 GB of JSON lines; nothing here ever
materializes it. Callers pass the ids they want and stop early once every one is
found — a full pass costs minutes, a partial pass seconds.
"""

import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Protocol fact, not a tunable: the single member the Kaggle snapshot zip holds.
SEED_MEMBER = "arxiv-metadata-oai-snapshot.json"

# Protocol fact: new-style arXiv ids ("2607.01234"), April 2007 onward.
_NEW_STYLE_ID = re.compile(r"^\d{4}\.\d{4,5}$")


def iter_records(seed_zip: Path, wanted_ids: set[str]) -> Iterator[dict[str, Any]]:
    """Yield each snapshot record whose `id` is in `wanted_ids`, then stop.

    Early exit on the last wanted id is what keeps a targeted lookup cheap; a
    caller wanting the whole catalog should not be using this function.
    """
    remaining = set(wanted_ids)
    if not remaining:
        return
    with zipfile.ZipFile(seed_zip) as archive, archive.open(SEED_MEMBER) as handle:
        for raw in handle:
            record = json.loads(raw)
            if record.get("id") in remaining:
                remaining.discard(record["id"])
                yield record
                if not remaining:
                    return


def first_version_year(record: dict[str, Any]) -> int | None:
    """The year of v1, from `versions[0].created`.

    NOT the OAI `<created>` datestamp, which is the LATEST version's date — a
    2018 paper revised in 2025 dates as 2025 there, which would misplace every
    foundation on the landing page by up to several years.
    """
    versions = record.get("versions") or []
    if not versions:
        return None
    created = versions[0].get("created", "")
    # RFC-822 style: "Mon, 3 Aug 2026 12:00:00 GMT" — the year is the token
    # before the clock, and is the only 4-digit field in that position.
    for token in reversed(created.split()):
        if len(token) == 4 and token.isdigit():
            return int(token)
    return None


def latest_version(record: dict[str, Any]) -> str | None:
    """The newest version tag ("v3"), for D9's version-pinned arxiv.org links."""
    versions = record.get("versions") or []
    return versions[-1].get("version") if versions else None


def count_cs_papers_by_id_month(seed_zip: Path) -> dict[str, int]:
    """Catalog census: cs-primary papers per id-month, for the whole snapshot.

    A FULL pass (measured 2026-09-15: 84 s over 3.1M records on this box),
    which is why it is a separate function from `iter_records` and its early
    exit: a denominator is a property of the catalog, not of any id set a
    caller could pass in.

    It is what lets the landing page say "12,216 of the 13,016 cs papers
    arXiv posted in July" instead of "every cs paper" — the latter was false
    by 6% in July and 25% in August, and nothing in the corpus could have
    told us so.

    cs-primary, matching how the collector selected papers
    (`arxiv_ingest.seed_records` filters on the categories string's prefix, so
    the FIRST category decides). New-style ids only: an id-month is what the
    page counts in, and old-style ids (`cs/0701001`) have none.
    """
    counts: dict[str, int] = {}
    with zipfile.ZipFile(seed_zip) as archive, archive.open(SEED_MEMBER) as handle:
        for raw in handle:
            record = json.loads(raw)
            arxiv_id = str(record.get("id") or "")
            if not _NEW_STYLE_ID.match(arxiv_id):
                continue
            categories = str(record.get("categories") or "")
            if not categories.startswith("cs."):
                continue
            month = arxiv_id.split(".")[0]
            counts[month] = counts.get(month, 0) + 1
    return counts
