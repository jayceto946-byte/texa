"""Compress frontend build assets only; never buffer API/SSE responses."""
import re

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class StaticAssetCompression:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1024, compresslevel=6)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get("path", "")
        headers = Headers(scope=scope) if scope["type"] == "http" else None
        async def cached_send(message):
            if (message['type'] == 'http.response.start'
                and message['status'] in (200, 206, 304)
                and re.fullmatch(r'/assets/[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8,}\.(?:js|css)', path)):
                message = dict(message)
                message['headers'] = list(message.get('headers', [])) + [
                    (b'cache-control', b'public, max-age=31536000, immutable'),
                ]
            await send(message)

        if (
            headers is not None
            and scope.get("method") == "GET"
            and path.startswith("/assets/")
            and path.endswith((".css", ".js"))
            and "range" not in headers
        ):
            await self.compressed(scope, receive, cached_send)
        else:
            await self.app(scope, receive, cached_send)
