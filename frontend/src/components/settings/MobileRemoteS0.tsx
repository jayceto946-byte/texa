import { useEffect, useState } from 'react';

export default function MobileRemoteS0() {
  const [status, setStatus] = useState<{ ready: boolean; target: string; instanceId: string; command: string }>();
  const [message, setMessage] = useState('');
  const load = () => window.kaoyanDesktop?.getRemoteS0Status?.().then(setStatus).catch(() => setMessage('无法读取连接信息，请重试。'));
  useEffect(() => {
    void load();
    return window.kaoyanDesktop?.onBackendStatus?.(() => { void load(); });
  }, []);
  if (!window.kaoyanDesktop?.getRemoteS0Status) return null;
  return <section className="settings-section">
    <h4 className="settings-section-title">手机远程连接 · S0</h4>
    <p className="settings-secondary">安装并登录 Tailscale 后，先检查 serve status 确认 443 未被其他服务使用，再手工执行下列命令。后端仅监听本机。</p>
    <p className="settings-secondary">{status?.ready ? '桌面服务已就绪' : '桌面托管服务尚未就绪'} · {status?.target}</p>
    {status?.ready && <code style={{ overflowWrap: 'anywhere' }}>{status.command}</code>}
    <div className="flex flex-wrap gap-2 pt-3">
      <button className="app-secondary-button" onClick={() => void load()}>刷新实际端口</button>
      <button className="app-secondary-button" disabled={!status?.ready} onClick={async () => {
        try { setMessage(await window.kaoyanDesktop?.copyRemoteS0Token?.() ? '临时管理令牌已复制。仅粘贴到本人手机连接页，之后清空剪贴板。桌面重启后需重新连接。' : '复制失败，请确认桌面服务已就绪。'); }
        catch { setMessage('复制失败，请重试。'); }
      }}>复制临时管理令牌</button>
    </div>
    {message && <p role="status" className="settings-secondary">{message}</p>}
  </section>;
}
