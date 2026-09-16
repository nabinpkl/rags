"""FastAPI assembly (#30/#27; spec §4c): lifespan, CORS, router mounting.

`routes_chat.py` and `routes_explorer.py` mount here. `routes_admin.py`
(spend dashboard) is a later issue (spec §4c tree).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from askrag import telemetry
from askrag.api.routes_catalog import router as catalog_router
from askrag.api.routes_census import router as census_router
from askrag.api.routes_chat import router as chat_router
from askrag.api.routes_explorer import router as explorer_router
from askrag.api.routes_landing import router as landing_router
from askrag.api.routes_thumbnails import router as thumbnails_router
from askrag.api.session_store import SessionStore
from askrag.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    telemetry.init(settings)
    # Nothing heavy to mint: corpus.db/chroma connections are per-call
    # factories (D4, askrag/db.py). The session store is the one
    # process-lifetime object this app owns (D13: single process, no Redis).
    app.state.session_store = SessionStore(settings=settings)
    try:
        yield
    finally:
        telemetry.shutdown()


app = FastAPI(title="askRAG API", lifespan=lifespan)

# CORS config is read once at app-definition time (Starlette requires
# middleware to be installed before the app starts serving; it cannot be
# added from inside lifespan) — same house-rule spirit as Depends-injected
# resources, just constrained by where Starlette lets middleware attach.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(explorer_router)
app.include_router(landing_router)
app.include_router(census_router)
app.include_router(catalog_router)
app.include_router(thumbnails_router)
