import asyncio
from types import SimpleNamespace


def test_packaged_shutdown_cancels_jobs_then_requests_uvicorn_exit(monkeypatch):
    import backend.api.system as system_api
    import backend.job_manager as job_manager

    server = SimpleNamespace(should_exit=False)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(desktop_server=server)))
    cancelled = []
    manager = SimpleNamespace(
        list_jobs=lambda limit=500: [
            {"id": "running-1", "status": "running"},
            {"id": "done-1", "status": "completed"},
        ],
        request_cancel=lambda job_id, message: cancelled.append((job_id, message)),
    )
    monkeypatch.setattr(job_manager, "get_job_manager", lambda: manager)

    async def run():
        result = await system_api.graceful_shutdown(request)
        await asyncio.sleep(0.25)
        return result

    result = asyncio.run(run())

    assert result["success"] is True
    assert result["cancelling_jobs"] == 1
    assert cancelled[0][0] == "running-1"
    assert server.should_exit is True
