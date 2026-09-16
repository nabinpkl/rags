"""GET /api/thumb/{arxiv_id} — the card image, rendered on first request.

The cache is the file (`ingest/render_thumbnails.py`). Caddy serves
`/thumbs/{arxiv_id}.jpg` straight off disk and falls through to this route
only when the file is absent, so this handler runs once per paper in the
life of the corpus and never again. That is what lets a new month of papers
show pictures the moment its PDFs land, with no reindex and no batch run
standing between the data and the page.

THIS ROUTE READS PDFs AND MUST NEVER RETURN ONE. It is the only serving path
with the PDF tree mounted, and §6b's line is that we do not serve e-prints:
the response is always a rendered JPEG, the arxiv_id is validated against a
literal id pattern before it reaches a path, and the PDF bytes never leave
the process. `test_routes_thumbnails.py` asserts both.

Nothing here touches arxiv.org. The image comes from the PDF we already
hold, because thirty cards rendering from arxiv.org would be thirty requests
per render — see CLAUDE.md's hard constraints.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Response

from askrag.config import Settings, get_settings
from askrag.ingest import render_thumbnails

_log = logging.getLogger("askrag.api.routes_thumbnails")

router = APIRouter()

# An arXiv id and nothing else. The id becomes a filename in two trees, so
# this is the boundary that keeps a traversal ("../../corpus.db") from ever
# being a path: it is a whitelist of the shape, not an escape of the input.
ARXIV_ID = re.compile(r"^[0-9]{4}\.[0-9]{4,5}$")

# A week in a browser, forever in a shared cache. The bytes for an id never
# change: a paper's v2 is a different e-print but the crop is of the version
# we hold, and re-rendering it is a `just thumbnails --force` away.
CACHE_CONTROL = "public, max-age=604800, immutable"


@router.get(
    "/api/thumb/{arxiv_id}",
    responses={200: {"content": {"image/jpeg": {}}}},
    response_class=Response,
)
def get_thumbnail(arxiv_id: str, settings: Settings = Depends(get_settings)) -> Response:
    """One paper's card image, rendering it if this is the first request."""
    arxiv_id = arxiv_id.removesuffix(".jpg")
    if not ARXIV_ID.match(arxiv_id):
        raise HTTPException(status_code=422, detail="not an arxiv id")
    try:
        path = render_thumbnails.thumbnail_for(
            arxiv_id,
            pdfs_dir=settings.pdfs_dir,
            thumbs_dir=settings.thumbs_dir,
            settings=settings,
        )
    except Exception as error:
        # A PDF that will not open is a fact about that paper, not a server
        # fault: the card falls back to its category glyph on a 404, and one
        # broken e-print must not read as the thumbnail service being down.
        #
        # Logged at WARNING with the reason, because the 404 alone is the same
        # answer for "this paper is corrupt" and "the cache directory is not
        # writable by this container" — one is per-paper and one is every
        # paper, and without this line they are indistinguishable from outside.
        _log.warning("thumbnail failed for %s: %s: %s", arxiv_id, type(error).__name__, error)
        raise HTTPException(status_code=404, detail="cannot render this paper") from error
    if path is None:
        raise HTTPException(status_code=404, detail="no pdf held for this paper")
    return Response(
        content=path.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": CACHE_CONTROL},
    )
