"""An ASGI response owns its producer, including disconnect cleanup."""
from functools import partial
from contextlib import contextmanager

import anyio
from starlette.responses import StreamingResponse


@contextmanager
def owned_provider_events(factory):
    from graph.main_graph import _iterate_stream_with_progress
    events = _iterate_stream_with_progress(factory, phase="reasoning", operation_id="provider",
                                          label="生成答案", summary="模型仍在处理当前问题")
    try:
        yield events
    finally:
        events.close()


def close_task_run(store, task, run_id):
    from backend.services.learning_task import interrupt_learning_task
    if task and store.run_is_active(task.id, run_id):
        interrupt_learning_task(store, task, stage="disconnected", expected_run_id=run_id)


class OwnedStreamingResponse(StreamingResponse):
    def __init__(self, content, *, on_close=None, **kwargs):
        self.producer = content
        self.on_close = on_close
        self.closed = False
        super().__init__(content, **kwargs)

    async def aclose(self):
        if self.closed:
            return
        self.closed = True
        with anyio.CancelScope(shield=True):
            if self.on_close:
                await anyio.to_thread.run_sync(self.on_close)
            try:
                async_close = getattr(self.producer, "aclose", None)
                if async_close:
                    await async_close()
                else:
                    close = getattr(self.producer, "close", None)
                    if close:
                        await anyio.to_thread.run_sync(close)
            except ValueError as exc:
                # A provider next() may still be running. Its owner closes it
                # on return; the task fence above already prevents late output.
                if "generator already executing" not in str(exc):
                    raise

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.aclose()


async def prepare_owned_response(factory, *args):
    # A cancelled preflight must still hand its new task/producer to its owner.
    with anyio.CancelScope(shield=True):
        return await anyio.to_thread.run_sync(partial(factory, *args))
