"""On-demand Tailscale observations. No background ping or network configuration.

Status is the daemon's recent path estimate, not proof of packet delivery. RTT
comes only from explicit disco probes and is kept separate from HTTP latency.
"""
from __future__ import annotations

import asyncio
import copy
import ipaddress
import json
import ntpath
import os
import re
import shutil
import sys
import time
from collections import deque
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def status_path(peer):
    if peer.get('Online') is False:
        return 'offline'
    if not peer.get('Active'):
        return 'unknown'  # idle endpoints can be stale; Relay alone proves nothing
    if peer.get('CurAddr'):
        return 'direct'
    if peer.get('PeerRelay'):
        return 'peer_relay'
    if peer.get('Relay'):
        return 'derp'
    return 'connecting'


def parse_pings(output):
    samples = []
    for line in output.splitlines():
        match = re.search(r'via (\S+) in ([\d.]+)(ms|s|µs|us)\b', line)
        if not match:
            continue
        via, value, unit = match.groups()
        path = 'unknown'
        region = None
        if via.startswith('DERP(') and via.endswith(')'):
            path, region = 'derp', via[5:-1]
        elif via.startswith('peer-relay('):
            path = 'peer_relay'
        else:
            try:
                # Direct CLI endpoint is IPv4:port or [IPv6]:port.
                host = via.rsplit(':', 1)[0].strip('[]')
                ipaddress.ip_address(host)
                path = 'direct'
            except ValueError:
                pass
        if path != 'unknown':
            ms = float(value) * {'ms': 1, 's': 1000, 'µs': .001, 'us': .001}[unit]
            if 0 <= ms <= 30000:
                samples.append({'path': path, 'rtt_ms': round(ms, 3), 'derp_region': region,
                                'source': 'tailscale_ping_disco', 'sampled_at': timestamp()})
    return samples


def find_cli():
    executable = shutil.which('tailscale')
    if executable:
        return executable
    if sys.platform == 'win32':
        roots = [os.getenv(name) for name in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)')]
        candidates = [ntpath.join(root, 'Tailscale', 'tailscale.exe') for root in [*roots, r'C:\Program Files'] if root]
    elif sys.platform == 'darwin':
        candidates = ['/Applications/Tailscale.app/Contents/MacOS/Tailscale', '/usr/local/bin/tailscale', '/opt/homebrew/bin/tailscale']
    else:
        candidates = ['/usr/bin/tailscale', '/usr/local/bin/tailscale']
    return next((candidate for candidate in dict.fromkeys(candidates) if os.path.isfile(candidate)), None)


async def run_cli(args, timeout):
    executable = find_cli()
    if not executable:
        raise RuntimeError('cli_unavailable')
    proc = await asyncio.create_subprocess_exec(executable, *args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode and not output:
        raise RuntimeError('cli_failed')
    # Raw status/output may contain user names, IPs, auth URLs; never return/log it.
    return output.decode('utf-8', errors='replace')


class ConnectionMonitor:
    def __init__(self, runner=run_cli, clock=time.monotonic):
        self.runner, self.clock = runner, clock
        self.lock = asyncio.Lock()
        self.cached_at = float('-inf')
        self.last_probe = float('-inf')
        self.peer_id = None
        self.current = None
        self.history = deque(maxlen=64)
        self.samples = deque(maxlen=64)
        self.changed_at = None

    def record(self, observation):
        before = self.current
        if not before or (before['path'], before.get('derp_region')) != (observation['path'], observation.get('derp_region')):
            self.changed_at = observation['sampled_at']
            self.history.append({**observation, 'previous_path': before['path'] if before else None})
            from backend.services.runtime_events import emit_best_effort
            emit_best_effort('state_transition', session_id='system.network', payload={
                'origin_kind': 'network_diagnostic', 'capability': 'tailscale',
                'status': observation['path'], 'phase': observation['source'],
                'reason_code': before['path'] if before else 'initial',
            })
        self.current = observation

    def payload(self, **extra):
        recent = self.samples[-1] if self.samples else None
        return {'observation': copy.deepcopy(self.current), 'changed_at': self.changed_at,
                'last_probe': copy.deepcopy(recent), 'history': list(self.history),
                'samples': list(self.samples), 'probe_cooldown_seconds': round(max(0, 60 - (self.clock() - self.last_probe))),
                'target_selected': self.peer_id is not None, **extra}

    async def _status(self):
        self.cached_at = self.clock()
        try:
            data = json.loads(await self.runner(['status', '--json'], 4))
            peers = list(data.get('Peer', {}).values())
            configured = os.getenv('TEXA_NETWORK_PEER_IP', '').strip()
            candidates = [p for p in peers if configured in p.get('TailscaleIPs', [])] if configured else [
                p for p in peers if p.get('OS', '').lower() in {'android', 'ios', 'ipados'}
            ]
            if data.get('BackendState') != 'Running':
                raise RuntimeError('daemon_not_running')
            if len(candidates) != 1:
                raise RuntimeError('peer_ambiguous' if len(candidates) > 1 else 'peer_not_found')
            peer = candidates[0]
            # Bind probes to a known tailnet peer, never caller-supplied destinations.
            target = configured or next(iter(peer.get('TailscaleIPs', [])), '')
            ipaddress.ip_address(target)
            if self.peer_id != target:
                self.samples.clear()
                self.history.clear()
                self.current = None
            self.peer_id = target
            path = status_path(peer)
            observation = {'path': path, 'source': 'tailscale_status', 'sampled_at': timestamp(),
                           'home_derp': peer.get('Relay') or None,
                           'derp_region': peer.get('Relay') if path == 'derp' else None,
                           'error_code': None}
        except (ValueError, TypeError, AttributeError, OSError, RuntimeError, asyncio.TimeoutError) as exc:
            self.peer_id = None
            observation = {'path': 'unknown', 'source': 'tailscale_status', 'sampled_at': timestamp(),
                           'home_derp': None, 'derp_region': None,
                           'error_code': str(exc) if isinstance(exc, RuntimeError) else 'status_unavailable'}
        self.record(observation)

    async def observe(self):
        async with self.lock:
            if self.clock() - self.cached_at >= 15:
                await self._status()
            return self.payload()

    async def probe(self):
        async with self.lock:
            if self.clock() - self.last_probe < 60:
                return self.payload(probe_result='cooldown')
            await self._status()
            if not self.peer_id:
                return self.payload(probe_result='unavailable')
            if self.current['path'] == 'offline':
                return self.payload(probe_result='offline')
            self.last_probe = self.clock()
            try:
                # Three attempts in <= 10s. Do not rely on --until-direct for
                # stopping: some versions also stop on a peer relay result.
                output = await self.runner(['ping', '--c=3', '--timeout=2s', '--until-direct=false', self.peer_id], 10)
                samples = parse_pings(output)
            except (OSError, RuntimeError, asyncio.TimeoutError):
                samples = []
            for sample in samples:
                self.samples.append(sample)
                self.record({**sample, 'home_derp': self.current.get('home_derp'), 'error_code': None})
            if not samples:
                self.record({'path': 'unknown', 'source': 'tailscale_ping_disco', 'sampled_at': timestamp(),
                             'home_derp': self.current.get('home_derp'), 'derp_region': None, 'error_code': 'probe_no_reply'})
            self.cached_at = float('-inf')
            result = 'direct_observed' if samples and samples[-1]['path'] == 'direct' else 'relay_observed' if samples else 'no_reply'
            return self.payload(probe_result=result)


monitor = ConnectionMonitor()
