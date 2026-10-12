import asyncio
import json

import pytest

from backend.services.network_diagnostics import ConnectionMonitor, parse_pings, status_path


@pytest.mark.parametrize('peer,expected', [
    ({'Online': True, 'Relay': 'sfo'}, 'unknown'),
    ({'Online': True, 'Active': True, 'Relay': 'sfo', 'CurAddr': '1.2.3.4:42'}, 'direct'),
    ({'Online': True, 'Active': True, 'Relay': 'sfo', 'PeerRelay': '1.2.3.4:42:1'}, 'peer_relay'),
    ({'Online': True, 'Active': True, 'Relay': 'sfo'}, 'derp'),
    ({'Online': False, 'Active': True, 'CurAddr': 'stale'}, 'offline'),
    ({'Online': True, 'Active': True}, 'connecting'),
])
def test_status_not_home_derp(peer, expected):
    assert status_path(peer) == expected


def test_cli_samples_separate_initial_and_direct_rtt():
    output = '\n'.join(['pong from phone via DERP(sfo) in 1.651s',
                        'pong from phone via 1.2.3.4:5678 in 44ms',
                        'pong from phone via [2001:db8::1]:123 in 42ms',
                        'pong from phone via peer-relay(100.64.1.2:1:vni:1) in 50ms',
                        'pong from phone via disco in 1ms', 'ping timed out'])
    samples = parse_pings(output)
    assert [s['path'] for s in samples] == ['derp', 'direct', 'direct', 'peer_relay']
    assert [s['rtt_ms'] for s in samples] == [1651, 44, 42, 50]
    assert '1.2.3.4' not in str(samples)


def peer(**changes):
    return {'OS': 'android', 'TailscaleIPs': ['100.119.253.35'], 'Online': True,
            'Active': True, 'Relay': 'sfo', **changes}


def test_upgrade_degrade_idle_resume_cooldown_and_no_passive_ping(monkeypatch):
    monkeypatch.delenv('TEXA_NETWORK_PEER_IP', raising=False)
    monkeypatch.setattr('backend.services.runtime_events.emit_best_effort', lambda *a, **kw: '')
    now = [100.]
    state = [peer()]
    calls = []
    async def runner(args, timeout):
        calls.append(args)
        if args[0] == 'status':
            return json.dumps({'BackendState': 'Running', 'Peer': {'key': state[0]}})
        return 'pong via DERP(sfo) in 1651ms\npong via 1.2.3.4:45 in 44ms'
    async def scenario():
        monitor = ConnectionMonitor(runner, lambda: now[0])
        assert (await monitor.observe())['observation']['path'] == 'derp'
        await monitor.observe()
        assert len(calls) == 1
        result = await monitor.probe()
        assert result['probe_result'] == 'direct_observed'
        assert result['last_probe']['rtt_ms'] == 44
        assert result['history'][-1]['previous_path'] == 'derp'
        assert (await monitor.probe())['probe_result'] == 'cooldown'
        now[0] += 16
        assert (await monitor.observe())['observation']['path'] == 'derp'
        state[0] = peer(Active=False, CurAddr='stale')
        now[0] += 16
        assert (await monitor.observe())['observation']['path'] == 'unknown'
        state[0] = peer(CurAddr='2.3.4.5:10')
        now[0] += 16
        assert (await monitor.observe())['observation']['path'] == 'direct'
        assert sum(c[0] == 'ping' for c in calls) == 1
        assert len(monitor.history) <= 64
    asyncio.run(scenario())


def test_unavailable_ambiguous_and_configured_target(monkeypatch):
    monkeypatch.setattr('backend.services.runtime_events.emit_best_effort', lambda *a, **kw: '')
    async def scenario():
        async def failure(*args):
            raise RuntimeError('cli_failed')
        monitor = ConnectionMonitor(failure)
        assert (await monitor.observe())['observation']['error_code'] == 'cli_failed'
        assert (await monitor.probe())['probe_result'] == 'unavailable'
        async def multiple(*args):
            return json.dumps({'BackendState': 'Running', 'Peer': {'one': peer(), 'two': peer(TailscaleIPs=['100.64.0.2'])}})
        monkeypatch.delenv('TEXA_NETWORK_PEER_IP', raising=False)
        monitor = ConnectionMonitor(multiple)
        assert (await monitor.observe())['observation']['error_code'] == 'peer_ambiguous'
        monkeypatch.setenv('TEXA_NETWORK_PEER_IP', '100.119.253.35')
        monitor = ConnectionMonitor(multiple)
        assert (await monitor.observe())['target_selected']
        monkeypatch.setenv('TEXA_NETWORK_PEER_IP', '; bad command')
        assert (await monitor.probe())['probe_result'] == 'unavailable'
    asyncio.run(scenario())


def test_probe_timeout_does_not_claim_direct(monkeypatch):
    monkeypatch.delenv('TEXA_NETWORK_PEER_IP', raising=False)
    monkeypatch.setattr('backend.services.runtime_events.emit_best_effort', lambda *a, **kw: '')
    async def runner(args, timeout):
        if args[0] == 'status':
            return json.dumps({'BackendState': 'Running', 'Peer': {'key': peer()}})
        raise asyncio.TimeoutError()
    async def scenario():
        result = await ConnectionMonitor(runner).probe()
        assert result['probe_result'] == 'no_reply'
        assert result['observation']['path'] == 'unknown'
        assert result['last_probe'] is None
    asyncio.run(scenario())


def test_network_routes_require_existing_token_and_do_not_cache(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.system import router
    from backend.security import LocalApiBoundaryMiddleware
    from backend.services import network_diagnostics
    monkeypatch.setenv('KAOYAN_REQUIRE_API_TOKEN', '1')
    monkeypatch.setenv('KAOYAN_API_TOKEN', 'diagnostic-test')
    class FakeMonitor:
        async def observe(self):
            return {'observation': {'path': 'unknown'}}
        async def probe(self):
            return {'probe_result': 'relay_observed'}
    monkeypatch.setattr(network_diagnostics, 'monitor', FakeMonitor())
    app = FastAPI()
    app.add_middleware(LocalApiBoundaryMiddleware)
    app.include_router(router, prefix='/api')
    client = TestClient(app)
    assert client.get('/api/system/network-diagnostics').status_code == 401
    assert client.post('/api/system/network-diagnostics/probe', json={}).status_code == 401
    for method, route in [(client.get, ''), (client.post, '/probe')]:
        result = method('/api/system/network-diagnostics' + route, headers={'X-Kaoyan-Token': 'diagnostic-test'})
        assert result.status_code == 200
        assert result.headers['cache-control'] == 'no-store'
