"""Cache-Control on the API's GET answers, so an edge cache can serve them.

Every GET under /api reads the corpus snapshot, which changes only when the
index is rebuilt and redeployed (D12), so the same URL gives the same bytes
for the life of a deploy. Without a header no shared cache keeps them, and
each page view re-runs ~1 s queries on the box. Only a 200 is marked: an
error is about this moment, not the snapshot. A route that sets its own
header (thumbnails) keeps it, and POST /api/chat is never touched.

Plain ASGI rather than `@app.middleware("http")`: Starlette's
BaseHTTPMiddleware wraps every response body, the chat SSE stream included,
and this has no business near that stream.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ApiCacheHeaders:
    def __init__(self, app: ASGIApp, *, cache_control: str) -> None:
        self.app = app
        self.cache_control = cache_control

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "GET"
            or not scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 200:
                headers = MutableHeaders(scope=message)
                if "cache-control" not in headers:
                    headers["Cache-Control"] = self.cache_control
            await send(message)

        await self.app(scope, receive, send_with_header)
