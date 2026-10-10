from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from askrag.api.cache_headers import ApiCacheHeaders

POLICY = "public, max-age=1"


def make_client() -> TestClient:
    app = FastAPI()

    @app.get("/api/landing")
    def landing() -> dict:
        return {"ok": True}

    @app.get("/api/missing")
    def missing() -> Response:
        return Response(status_code=404)

    @app.get("/api/thumb")
    def thumb() -> Response:
        return Response(headers={"Cache-Control": "immutable"})

    @app.post("/api/chat")
    def chat() -> dict:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    app.add_middleware(ApiCacheHeaders, cache_control=POLICY)
    return TestClient(app)


def test_a_successful_api_read_is_marked_cacheable():
    assert make_client().get("/api/landing").headers["cache-control"] == POLICY


def test_an_error_is_not_cached():
    assert "cache-control" not in make_client().get("/api/missing").headers


def test_a_route_that_sets_its_own_policy_keeps_it():
    assert make_client().get("/api/thumb").headers["cache-control"] == "immutable"


def test_chat_and_non_api_paths_are_left_alone():
    client = make_client()
    assert "cache-control" not in client.post("/api/chat").headers
    assert "cache-control" not in client.get("/health").headers
