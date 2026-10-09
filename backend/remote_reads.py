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
_TIMED = [
    (re.compile(r'^/api/jobs(?:/[^/]+)?$'), 'job-read'),
    (re.compile(r'^/api/system/health$'), 'system-health'),
    (re.compile(r'^/api/books/[^/]+/chapter-highlights(?:/[^/]+(?:/html)?)?$'), 'chapter-highlight'),
    (re.compile(r'^/api/notes(?:/[^/]+)*$'), 'notes-read'),
    (re.compile(r'^/api/chat/conversations/[^/]+/(?:messages|messages-after|message-context|management)$'), 'session-page'),
    (re.compile(r'^/api/books/[^/]+/(?:source-pdf|pdf)$'), 'textbook-pdf'),
    (re.compile(r'^/api/books/[^/]+/(?:figures(?:/[^/]+(?:/(?:image|group-image))?)?|chapters)$'), 'citation-read'),
    (re.compile(r'^/api/mistakes/(?:[^/]+|tasks/[^/]+|visual-tasks/[^/]+|drafts/[^/]+)/(?:image|attachments/[^/]+)$'), 'image-read'),
]
_DETAIL = re.compile(r'^/api/chat/conversations/[^/]+$')


class RemoteReadOptimization:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1024, compresslevel=6)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get('path', '')
        compressed_label = _LABELS.get(path) or ('session-detail' if _DETAIL.fullmatch(path) else None)
        label = compressed_label or next((name for pattern, name in _TIMED if pattern.fullmatch(path)), None)
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
                ]
                if compressed_label:
                    message['headers'].append((b'cache-control', b'no-store'))
            if message['type'] == 'http.response.body':
                size += len(message.get('body', b''))
            await send(message)
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                # Labels and numbers only: no query, identity, credential or content.
                _logger.info('%s read %s status=%d app_header_ms=%.1f response_body_bytes=%d',
                             'S0' if compressed_label else 'S2', label, status, header_ms, size)

        # Timing-only for new finite routes: preserve existing compression, ranges and cache headers.
        await (self.compressed if compressed_label else self.app)(scope, receive, timed_send)
