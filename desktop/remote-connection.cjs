const fs = require('node:fs');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const runFile = promisify(execFile);

function createRemoteConnection({ statePath, getTarget, isReady, run = async (file, args) => {
  const result = await runFile(file, args, { timeout: 15000, maxBuffer: 2 * 1024 * 1024, windowsHide: true });
  return result.stdout;
}, platform = process.platform }) {
  let busy = false;
  let cli;
  const read = () => { try { return JSON.parse(fs.readFileSync(statePath, 'utf8')); } catch { return {}; } };
  const save = (value) => fs.writeFileSync(statePath, JSON.stringify(value), { mode: 0o600 });
  async function command(args) {
    if (cli) { try { return await run(cli, args); } catch { throw new Error('连接操作未完成，请确认 Tailscale 已登录且允许 HTTPS 共享。'); } }
    const candidates = platform === 'darwin' ? ['/Applications/Tailscale.app/Contents/MacOS/Tailscale', '/usr/local/bin/tailscale', '/opt/homebrew/bin/tailscale', 'tailscale'] : platform === 'win32' ? [String(process.env.ProgramFiles || 'C:\\Program Files') + '\\Tailscale\\tailscale.exe', 'tailscale.exe'] : ['tailscale', '/usr/bin/tailscale'];
    for (const candidate of candidates) {
      try { const result = await run(candidate, args); cli = candidate; return result; }
      catch (error) { if (error.code !== 'ENOENT') throw new Error('无法连接 Tailscale，请确认它已打开并登录。'); }
    }
    throw new Error('请先安装并打开 Tailscale，再重试连接。');
  }
  async function inspect() {
    const node = JSON.parse(await command(['status', '--json']));
    if (node.BackendState !== 'Running') throw new Error('请在 Tailscale 中登录并开启连接。');
    const dns = String(node.Self?.DNSName || '').replace(/\.$/, '');
    if (!/^[a-zA-Z0-9.-]+\.ts\.net$/.test(dns)) throw new Error('尚未取得安全连接地址，请稍后重试。');
    const config = JSON.parse(await command(['serve', 'status', '--json']));
    const routes = Object.entries(config.Web || {}).filter(([host]) => host.endsWith(':443')).flatMap(([host, value]) => Object.entries(value.Handlers || {}).map(([path, handler]) => ({ host, path, proxy: handler.Proxy })));
    const funnel = Object.values(config.AllowFunnel || {}).some(Boolean);
    return { dns, config, routes, funnel };
  }
  async function status() {
    const base = { ready: isReady(), enabled: false, url: '', message: '', target: getTarget() };
    try {
      const data = await inspect();
      const enabled = !data.funnel && data.routes.some(route => route.host === data.dns + ':443' && route.path === '/' && route.proxy === getTarget());
      return { ...base, enabled, url: 'https://' + data.dns + '/', message: enabled ? '手机连接已开启' : '手机连接未开启' };
    } catch (error) { return { ...base, message: error.message }; }
  }
  async function setEnabled(enabled) {
    if (busy) throw new Error('连接正在更新，请稍候。');
    if (!isReady()) throw new Error('桌面服务尚未就绪，请稍后重试。');
    busy = true;
    try {
      const target = new URL(getTarget());
      if (target.protocol !== 'http:' || !['127.0.0.1','localhost'].includes(target.hostname) || target.pathname !== '/' || target.username || target.password) throw new Error('手机连接仅支持当前桌面的本地服务。');
      const data = await inspect();
      const previous = read();
      if (data.funnel) throw new Error('检测到公网共享配置，请先在 Tailscale 中关闭公网共享。');
      // Own only the root handler. Never reset all Serve settings or replace another service.
      const activeRoutes = data.routes.filter(route => route.host === data.dns + ':443');
      const roots = activeRoutes.filter(route => route.path === '/');
      if (roots.some(route => route.proxy !== getTarget() && route.proxy !== previous.target)) throw new Error('远程连接入口被其他服务占用，请在 Tailscale 中调整后重试。');
      if (data.config.TCP?.['443'] && !data.config.TCP['443'].HTTPS) throw new Error('443 已被其他服务占用。');
      if (!enabled && activeRoutes.some(route => route.path !== '/')) throw new Error('当前入口还有其他服务，请在 Tailscale 中单独关闭 Texa。');
      if (enabled) {
        await command(['serve', '--bg', '--https=443', '--yes', getTarget()]);
        save({ enabled: true, target: getTarget() });
      } else {
        if (roots.length) await command(['serve', '--https=443', 'off']);
        save({ enabled: false, target: getTarget() });
      }
      const result = await status();
      if (result.enabled !== enabled) throw new Error('连接状态尚未确认，请刷新后检查。');
      return result;
    } finally { busy = false; }
  }
  return { status, setEnabled, restore: async () => { if (read().enabled) return setEnabled(true); } };
}
module.exports = { createRemoteConnection };
