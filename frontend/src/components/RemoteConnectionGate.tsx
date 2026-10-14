import { useEffect, useState, type ReactNode } from 'react';
import { get, isRemoteBrowser, setConnectionToken } from '../api/client';
import './Welcome.css';

/** S0 connects to the running desktop; it never configures models on the phone. */
export default function RemoteConnectionGate({ children }: { children: ReactNode }) {
  const remote = isRemoteBrowser();
  const [ready, setReady] = useState(!remote);
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(remote);
  const [error, setError] = useState('');

  async function connect() {
    if (window.location.protocol !== 'https:') {
      setError('请使用 Tailscale Serve 提供的 HTTPS 地址连接。'); setBusy(false); return;
    }
    setBusy(true); setError('');
    try {
      const response = await get('/system/remote-ready');
      if (!response.success || !response.data?.token_required) throw new Error('桌面服务未强制启用 API token，请在桌面端检查启动方式。');
      if (!response.data.ready) throw new Error('请先在 Texa Desktop 完成回答模型配置，再重新连接。');
      setReady(true);
    } catch (reason) {
      setError(reason instanceof TypeError
        ? '无法连接桌面。请检查 Tailscale、Serve 映射及 Texa Desktop 是否仍在运行。'
        : reason instanceof Error ? reason.message : '连接失败，请重试。');
    } finally { setBusy(false); }
  }

  useEffect(() => {
    if (!remote) return;
    void connect();
    const unauthorized = () => { setReady(false); setToken(''); setError('令牌无效或已失效，请从当前运行的桌面端重新复制。'); };
    window.addEventListener('texa:connection-unauthorized', unauthorized);
    return () => window.removeEventListener('texa:connection-unauthorized', unauthorized);
    // Only initial bootstrap; retries are explicit to avoid resubmitting work.
  }, [remote]);

  if (ready) return children;
  return <div className="welcome-screen">
    <header className="welcome-brand"><div className="welcome-brand-group"><img src="/brand/texa-mark.svg" alt="" /><span>Texa</span></div></header>
    <main className="welcome-main"><form className="welcome-content" onSubmit={(event) => {
      event.preventDefault(); if (token.trim()) setConnectionToken(token); setToken(''); void connect();
    }}>
      <h1>连接 Texa Desktop</h1>
      <p className="welcome-lead">使用已运行的桌面教材与会话。模型配置请在桌面端完成。</p>
      <label htmlFor="remote-token">临时访问令牌</label>
      <input id="remote-token" type="password" autoComplete="off" spellCheck={false} value={token}
        onChange={(event) => setToken(event.target.value)} className="app-field" style={{ width: '100%', margin: '12px 0' }} />
      <p className="welcome-note">S0 仅限本人手机验证。管理令牌拥有完整权限，仅保留在当前浏览器会话；请勿分享或截图。</p>
      <button type="submit" className="app-primary-button welcome-primary" disabled={busy}>{busy ? '正在连接…' : '连接 / 重试'}</button>
      {error && <p role="alert" className="welcome-error">{error}</p>}
    </form></main>
  </div>;
}
