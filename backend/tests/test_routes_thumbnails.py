"""routes_thumbnails: the card image, rendered on the first request for it."""

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from askrag.api import routes_thumbnails
from askrag.config import Settings, get_settings


def _pdf(path, *, figure=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 96), "A Paper About Something", fontsize=18)
    if figure:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 300))
        pixmap.set_rect(pixmap.irect, (40, 90, 160))
        page.insert_image(pymupdf.Rect(72, 300, 372, 500), pixmap=pixmap)
    doc.save(path)
    doc.close()


@pytest.fixture
def client(tmp_path):
    _pdf(tmp_path / "pdfs" / "2026" / "08" / "2608.00001.pdf", figure=True)
    settings = Settings(
        traces_db_path=tmp_path / "traces.db",
        corpus_dir=tmp_path,
        _env_file=None,  # ty: ignore[unknown-argument]
    )
    app = FastAPI()
    app.include_router(routes_thumbnails.router)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def thumbs(tmp_path):
    """The cache directory, which pytest hands both fixtures the same root for."""
    return tmp_path / "thumbs"


def test_the_first_request_renders_the_image_and_the_next_one_finds_it_cached(client, thumbs):
    """The cache is the file, so nothing has to run before the page works:
    a paper's card image exists the first time anyone looks at it."""
    assert not (thumbs / "2608.00001.jpg").exists()

    first = client.get("/api/thumb/2608.00001")

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert (thumbs / "2608.00001.jpg").read_bytes() == first.content
    assert client.get("/api/thumb/2608.00001").content == first.content


def test_the_response_is_an_image_and_never_the_pdf(client, thumbs):
    """§6b: this is the only serving path with the PDF tree mounted, and the
    line it must hold is that an e-print never leaves it. The body is a JPEG
    the size of a thumbnail, not a PDF the size of a paper."""
    body = client.get("/api/thumb/2608.00001").content

    assert not body.startswith(b"%PDF")
    assert body.startswith(b"\xff\xd8\xff")  # JPEG SOI
    assert pymupdf.Pixmap(thumbs / "2608.00001.jpg").width <= 400


def test_the_url_suffix_is_accepted_because_caddy_passes_the_filename(client):
    """Caddy rewrites /thumbs/2608.00001.jpg to this route with the name
    intact, so the route takes the id with or without the extension."""
    assert client.get("/api/thumb/2608.00001.jpg").status_code == 200


def test_a_paper_we_hold_no_pdf_for_is_a_404_rather_than_an_error(client):
    """The card treats it as "no image" and shows its category glyph."""
    assert client.get("/api/thumb/2608.09999").status_code == 404


def test_an_unopenable_pdf_is_that_paper_s_problem_not_the_service_s(client, tmp_path):
    (tmp_path / "pdfs" / "2026" / "08" / "2608.00002.pdf").write_bytes(b"not a pdf")

    assert client.get("/api/thumb/2608.00002").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "../corpus.db",
        "..%2fcorpus.db",
        "2608.00001/../../corpus.db",
        "corpus.db",
        "2608",
        "2608.00001v2",
    ],
)
def test_only_something_shaped_like_an_arxiv_id_becomes_a_path(client, path):
    """The id becomes a filename in the PDF tree and the cache, so the shape
    is whitelisted before it is used rather than escaped after."""
    assert client.get(f"/api/thumb/{path}").status_code in (404, 422)
