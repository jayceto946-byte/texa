import httpx

from ingestion.mineru_runtime import inspect_mineru_runtime


def test_mineru_runtime_reports_unconfigured():
    assert inspect_mineru_runtime("", "") == {
        "configured": False,
        "available": False,
        "mode": "none",
        "reason": "not_configured",
    }


def test_mineru_runtime_probes_configured_api(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url):
            assert url == "http://mineru.test"
            return httpx.Response(404)

    monkeypatch.setattr(httpx, "Client", FakeClient)

    result = inspect_mineru_runtime("http://mineru.test", "")

    assert result == {
        "configured": True,
        "available": True,
        "mode": "api",
        "reason": "ready",
    }


def test_mineru_runtime_reports_missing_cli(monkeypatch):
    monkeypatch.setattr("ingestion.mineru_runtime.shutil.which", lambda _value: None)

    result = inspect_mineru_runtime("", "missing-mineru --output {output}")

    assert result["configured"] is True
    assert result["available"] is False
    assert result["mode"] == "cli"
    assert result["reason"] == "cli_missing"
