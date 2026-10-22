import { useCallback, useEffect, useRef, useState } from 'react';
import { networkStrategy, queryNetwork, setNetworkStrategy, type NetworkDiagnostics as Data, type NetworkPath } from '../../api/networkDiagnostics';

const paths: Record<NetworkPath, string> = { direct: 'Direct', peer_relay: 'Peer Relay', derp: 'DERP', connecting: 'Connecting', offline: 'Offline', unknown: 'Unknown' };
const outcomes: Record<string, string> = { direct_observed: '本次检测已观察到直连。', relay_observed: '本次检测仍使用中继，访问可继续。', no_reply: '探测未收到回复，请检查连接；未确认直连。', offline: '手机当前离线。', unavailable: '无法确定目标设备或读取 Tailscale。', cooldown: '检测处于冷却期，请稍后重试。' };
function time(value?: string) { return value ? new Date(value).toLocaleTimeString() : '—'; }

export default function NetworkDiagnostics({ active }: { active: boolean }) {
  const [data, setData] = useState<Data>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [strategy, setStrategy] = useState(networkStrategy);
  const [httpMs, setHttpMs] = useState<number>();
  const mounted = useRef(false);
  const inflight = useRef(false);
  const load = useCallback(async (probe = false) => {
    if (inflight.current) return;
    inflight.current = true;
    setBusy(true);
    const start = performance.now();
    try {
      const next = await queryNetwork(probe);
      if (!mounted.current) return;
      setData(next);
      setHttpMs(Math.round(performance.now() - start));
      setMessage(probe ? outcomes[next.probe_result || 'unavailable'] : '');
    } catch {
      if (mounted.current) setMessage('无法连接桌面诊断服务。请恢复网络后重新检测；学习会话仍保留。');
    } finally {
      inflight.current = false;
      if (mounted.current) setBusy(false);
    }
  }, []);
  useEffect(() => {
    if (!active) return;
    mounted.current = true;
    const refresh = () => { if (document.visibilityState === 'visible' && navigator.onLine) void load(); };
    refresh();
    const timer = window.setInterval(refresh, 30000);
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('online', refresh);
    return () => { mounted.current = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); window.removeEventListener('online', refresh); };
  }, [active, load]);
  const observation = data?.observation;
  const connected = observation && ['direct', 'derp', 'peer_relay'].includes(observation.path);
  const last = data?.last_probe;
  return <section className="settings-section">
    <h4 className="settings-section-title">网络连接</h4>
    <p role="status" className="settings-secondary">{connected ? '最近观察到连接路径' : observation?.path === 'offline' ? 'Tailscale 报告设备离线' : '连接状态待确认'} · {time(observation?.sampled_at)}</p>
    <p className="settings-secondary">最近检测延迟：{last?.rtt_ms === undefined ? '尚未测量' : `${last.rtt_ms} ms（${time(last.sampled_at)}）`}。检测可能促成连接恢复，历史延迟不代表当前延迟。</p>
    <div className="flex flex-wrap gap-2 pt-3">
      <button type="button" className="app-secondary-button" disabled={busy} onClick={() => void load()}>重新读取连接</button>
      <button type="button" className="app-secondary-button" disabled={busy || !data?.target_selected} onClick={() => void load(true)}>{busy ? '检测中…' : '检测并尝试优化'}</button>
    </div>
    <label className="settings-secondary" style={{ display: 'block', marginTop: 12 }}>
      <input type="checkbox" checked={strategy === 'prefer_direct'} onChange={event => { const next = event.target.checked ? 'prefer_direct' : 'auto'; setStrategy(next); setNetworkStrategy(next); }} /> 恢复连接时自动优化（当前浏览器会话）
    </label>
    <p className="settings-secondary">默认由 Tailscale 自动连接。自动优化仅在恢复前台或网络恢复时进行有限检测，失败时仍允许中继访问。</p>
    {message && <p role="status" className="settings-secondary">{message}</p>}
    <details style={{ marginTop: 12 }}>
      <summary>开发诊断 · Network Diagnostics</summary>
      <p className="settings-secondary">当前路径估计：{observation ? paths[observation.path] : 'Unknown'} · {observation?.path === 'direct' ? '已观察到 Direct' : '未确认 Direct'}。空闲时返回 Unknown，状态读取不验证包交付。</p>
      <p className="settings-secondary">来源：{observation?.source || '—'} · Home DERP：{observation?.home_derp || '—'}（不等于当前路径） · 当前中继区域：{observation?.derp_region || '—'}</p>
      <p className="settings-secondary">策略：{strategy === 'auto' ? 'Auto' : 'Prefer Direct（应用层有界探测）'} · 最近切换：{time(data?.changed_at)} · 冷却：{data?.probe_cooldown_seconds ?? 0} 秒</p>
      <p className="settings-secondary">最近探测路径：{last ? paths[last.path] : '—'} · RTT 来源：Tailscale disco ping。诊断 HTTP 完整耗时：{httpMs ?? '—'} ms（含电脑执行时间，非网络 RTT）。</p>
      {observation?.error_code && <p className="settings-secondary">诊断代码：{observation.error_code}。电脑端可通过 TEXA_NETWORK_PEER_IP 指定目标；未配置时自动识别唯一 Android、iPhone 或 iPad。存在多个候选设备时需指定目标；诊断不可用不代表设备无法访问 Texa。</p>}
      <p className="settings-secondary">不提供强制 Direct、DERP 区域选择或 Peer Relay 切换。DERP Map 与 Peer Relay 授权属于 Tailnet 配置，本功能不修改这些配置。</p>
      <ul className="settings-secondary">{data?.history.slice(-8).reverse().map((entry, index) => <li key={`${entry.sampled_at}-${index}`}>{time(entry.sampled_at)} · {entry.previous_path ? paths[entry.previous_path] : '初始'} → {paths[entry.path]} · {entry.source}{entry.derp_region ? ` (${entry.derp_region})` : ''}</li>)}</ul>
      <p className="settings-secondary">记录仅在后端当前进程中保留最近 64 项；切换事件写入现有 RuntimeEvent（不含设备地址）。默认不持续 Ping，锁屏保持情况需实机验收。</p>
    </details>
  </section>;
}
