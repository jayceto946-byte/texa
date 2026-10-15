import { useCallback, useEffect, useState } from 'react';
import { Copy, Loader2, Smartphone, RefreshCw } from 'lucide-react';
import type { DesktopRemoteConnection } from '../../types/electron';

export default function MobileRemoteS0() {
  const [status, setStatus] = useState<DesktopRemoteConnection>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setStatus(await window.kaoyanDesktop?.getRemoteS0Status?.()); }
    catch { setMessage('无法读取连接状态，请重试。'); }
  }, []);
  useEffect(() => { void load(); return window.kaoyanDesktop?.onBackendStatus?.(() => void load()); }, [load]);
  if (!window.kaoyanDesktop?.getRemoteS0Status) return null;
  async function toggle() {
    setBusy(true); setMessage('');
    try { setStatus(await window.kaoyanDesktop?.setRemoteConnectionEnabled?.(!status?.enabled)); }
    catch (error) { setMessage(error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': Error: /, '') : '连接未完成，请重试。'); }
    finally { setBusy(false); }
  }
  async function copy(token = false) {
    try {
      const copied = token ? await window.kaoyanDesktop?.copyRemoteS0Token?.() : await window.kaoyanDesktop?.copyRemoteConnectionUrl?.();
      setMessage(copied ? token ? '配对码已复制，请粘贴到本人手机连接页。桌面重启后需重新配对。' : '连接地址已复制，可发送到自己的手机打开。' : '未能复制，请重试。');
    } catch { setMessage('未能复制，请重试。'); }
  }
  return <section className="remote-connection settings-section" aria-label="手机连接">
    <div className="remote-connection-heading"><span className="remote-device-icon"><Smartphone size={24}/></span><div><h4 className="settings-section-title">连接这台电脑</h4><p className="settings-secondary">在手机上继续使用当前学习工作区</p></div><span className="remote-connection-state" data-enabled={status?.enabled}>{status?.enabled ? '已开启' : '未开启'}</span></div>
    <p className="settings-secondary">电脑和手机均开启 Tailscale，登录同一账户。连接开启后，在手机浏览器打开地址并配对。</p>
    <div className="remote-connection-actions"><button className="app-primary-button" disabled={busy || !status?.ready} onClick={() => void toggle()}>{busy ? <Loader2 size={16} className="animate-spin"/> : <Smartphone size={16}/>} {busy ? '正在连接…' : status?.enabled ? '关闭手机连接' : '开启手机连接'}</button><button className="app-ghost-button" disabled={busy} onClick={() => void load()} aria-label="刷新手机连接状态"><RefreshCw size={16}/></button></div>
    {status?.enabled && <div className="remote-pairing"><div><span className="settings-secondary">手机浏览器地址</span><a href={status.url} target="_blank" rel="noreferrer">{status.url.replace('https://','').replace(/\/$/,'')}</a></div><button className="app-secondary-button" onClick={() => void copy()}><Copy size={15}/>复制地址</button><button className="app-secondary-button" onClick={() => void copy(true)}>复制配对码</button></div>}
    <p role="status" className="settings-secondary">{message || status?.message || '正在读取连接状态…'}</p>
  </section>;
}
