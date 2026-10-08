"""Optimize finite S0 read responses without touching streaming endpoints."""
import logging
import re
from time import perf_counter

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

_LABELS = {
    '/api/chat/conversations': 'session-list',
    '/api/books/list': 'book-list',
    '/api/system/remote-ready': 'connection-ready',
}
_logger = logging.getLogger('uvicorn.error')
_DETAIL = re.compile(r'^/api/chat/conversations/[^/]+$')


class RemoteReadOptimization:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1024, compresslevel=6)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get('path', '')
        label = _LABELS.get(path) or ('session-detail' if _DETAIL.fullmatch(path) else None)
        if scope['type'] != 'http' or scope.get('method') != 'GET' or not label:
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        header_ms = 0.0
        status = 0
        size = 0

        async def timed_send(message):
            nonlocal header_ms, status, size
            if message['type'] == 'http.response.start':
                header_ms = (perf_counter() - started) * 1000
                status = message['status']
                message = dict(message)
                message['headers'] = list(message.get('headers', [])) + [
                    (b'server-timing', f'texa_read;dur={header_ms:.1f}'.encode('ascii')),
                    (b'cache-control', b'no-store'),
                ]
            if message['type'] == 'http.response.body':
                size += len(message.get('body', b''))
            await send(message)
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                # Labels and numbers only: no query, identity, credential or content.
                _logger.info('S0 read %s status=%d app_header_ms=%.1f wire_bytes=%d',
                             label, status, header_ms, size)

        await self.compressed(scope, receive, timed_send)
