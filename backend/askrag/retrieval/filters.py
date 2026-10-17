"""Search filters over any source's index (D8, D21): pushed down into both legs.

Source-agnostic by construction: a scope of document ids, a day range, and
exact-match facets the source declares (arXiv's `category`, a transcript's
`project`). A source maps its own vocabulary onto these (sources/arxiv.py
turns year_min=2024 into day_min=20240101); this module never names a source.
"""

import re
from dataclasses import dataclass

# Facet keys become Chroma metadata keys (`facet_<key>`) and SQL parameters;
# a closed spelling keeps both unsurprising.
_FACET_KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")


@dataclass(frozen=True)
class Filters:
    """None means no filter on that field."""

    # A scope, not a filter: `None` means unscoped, an EMPTY tuple means
    # nothing is in scope. Set server-side (a landing-page claim), never by
    # the model (§5/§6).
    doc_ids: tuple[str, ...] | None = None
    # Inclusive YYYYMMDD bounds on the document's day.
    day_min: int | None = None
    day_max: int | None = None
    # (key, value) pairs; a document must carry every pair.
    facets: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for key, _ in self.facets:
            if not _FACET_KEY.fullmatch(key):
                raise ValueError(f"facet key {key!r} is not a lowercase identifier")

    @property
    def empty_scope(self) -> bool:
        """True when the caller narrowed the scope to nothing at all."""
        return self.doc_ids is not None and not self.doc_ids
