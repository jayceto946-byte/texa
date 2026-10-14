import { get, post } from './client';
import { readBrowserStorage, writeBrowserStorage } from '../utils/browserStorage';

export type NetworkPath = 'direct' | 'peer_relay' | 'derp' | 'connecting' | 'offline' | 'unknown';
export type Observation = { path: NetworkPath; source: string; sampled_at: string; derp_region?: string; home_derp?: string; error_code?: string; rtt_ms?: number };
export type NetworkDiagnostics = { observation: Observation; changed_at: string; last_probe: Observation | null; history: (Observation & { previous_path: NetworkPath | null })[]; samples: Observation[]; target_selected: boolean; probe_cooldown_seconds: number; probe_result?: string };
export type NetworkStrategy = 'auto' | 'prefer_direct';
let strategy: NetworkStrategy = readBrowserStorage('sessionStorage', 'texa_network_strategy') === 'prefer_direct' ? 'prefer_direct' : 'auto';
const pending: Partial<Record<'read' | 'probe', Promise<NetworkDiagnostics>>> = {};
export function networkStrategy() { return strategy; }
export function setNetworkStrategy(value: NetworkStrategy) {
  strategy = value;
  writeBrowserStorage('sessionStorage', 'texa_network_strategy', value);
}
export function queryNetwork(probe = false): Promise<NetworkDiagnostics> {
  // Read-only recovery can retry once; probes and learning writes are never replayed.
  const key = probe ? 'probe' : 'read';
  if (pending[key]) return pending[key];
  pending[key] = (async () => {
    let response;
    if (probe) response = await post('/system/network-diagnostics/probe', {}, 15000);
    else {
      try { response = await get('/system/network-diagnostics', 6000); }
      catch (error) {
        if (!(error instanceof TypeError) || !navigator.onLine) throw error;
        response = await get('/system/network-diagnostics', 6000);
      }
    }
    return response.data as NetworkDiagnostics;
  })().finally(() => { delete pending[key]; });
  return pending[key];
}

/** No keepalive: resume events only, coalesced and bounded. */
export function installNetworkRecovery() {
  let stopped = false;
  let lastAttempt = -Infinity;
  const recover = async () => {
    if (document.visibilityState !== 'visible' || !navigator.onLine || Date.now() - lastAttempt < 60000) return;
    lastAttempt = Date.now();
    try {
      const data = await queryNetwork();
      if (!stopped && document.visibilityState === 'visible' && navigator.onLine && networkStrategy() === 'prefer_direct' && data.target_selected && !['direct', 'offline'].includes(data.observation.path)) {
        await queryNetwork(true);
      }
    } catch { /* Diagnostics cannot fence or resubmit learning tasks. */ }
  };
  window.addEventListener('online', recover);
  window.addEventListener('pageshow', recover);
  document.addEventListener('visibilitychange', recover);
  void recover();
  return () => {
    stopped = true;
    window.removeEventListener('online', recover);
    window.removeEventListener('pageshow', recover);
    document.removeEventListener('visibilitychange', recover);
  };
}
