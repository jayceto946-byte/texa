"""S0 loopback proxy authentication and read-only desktop readiness."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.security import LocalApiBoundaryMiddleware
from backend.api import system


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('KAOYAN_REQUIRE_API_TOKEN', '1')
    monkeypatch.setenv('KAOYAN_API_TOKEN', 's0-test-secret')
    monkeypatch.setattr(system, 'profiles_payload', lambda: {
        'roles': {'reasoning': {'model': 'test'}},
        'credentials': {'reasoning': {'required': True, 'configured': True}},
        'secret': 'must-not-be-returned',
    })
    app = FastAPI()
    app.add_middleware(LocalApiBoundaryMiddleware)
    app.include_router(system.router, prefix='/api')
    return TestClient(app)


def test_proxy_loopback_still_requires_token(client):
    for token in ('', 'wrong'):
        response = client.get('/api/system/remote-ready', headers={
            'X-Kaoyan-Token': token, 'Origin': 'https://texa.example.ts.net',
            'X-Forwarded-For': '127.0.0.1',
        })
        assert response.status_code == 401
        assert response.json()['error_code'] == 'INVALID_API_TOKEN'


def test_ready_response_has_no_settings_or_credentials(client):
    response = client.get('/api/system/remote-ready', headers={'X-Kaoyan-Token': 's0-test-secret'})
    assert response.json() == {'success': True, 'data': {'ready': True, 'token_required': True}}


def test_phone_cannot_treat_unconfigured_desktop_as_ready(client, monkeypatch):
    monkeypatch.setattr(system, 'profiles_payload', lambda: {
        'roles': {'reasoning': {'model': 'test'}},
        'credentials': {'reasoning': {'required': True, 'configured': False}},
    })
    assert not client.get('/api/system/remote-ready', headers={'X-Kaoyan-Token': 's0-test-secret'}).json()['data']['ready']


def test_insecure_development_start_is_not_remote_ready(client, monkeypatch):
    monkeypatch.setenv('KAOYAN_REQUIRE_API_TOKEN', '0')
    assert not client.get('/api/system/remote-ready').json()['data']['token_required']
