const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const runFile = promisify(execFile);

function connectionError(code, message) {
  return Object.assign(new Error(message), { code });
}

function commandError(error, args) {
  // Classify locally; never expose raw output, which can contain login URLs or credentials.
  const detail = [error.stdout, error.stderr, error.message].join('\n');
  if (/https.*(?:not enabled|disabled|must be enabled)|(?:enable|enabling) https|serve is not enabled|\/f\/serve/i.test(detail)) {
    return connectionError('https_required', 'Tailscale HTTPS 共享尚未启用。请在 Tailscale 管理后台的 DNS 设置中启用 HTTPS Certificates，再重试。');
  }
  if (['EACCES', 'EPERM'].includes(error.code) || /access (?:is )?denied|permission denied|not permitted|requires? (?:admin|elevation)|拒绝访问/i.test(detail)) {
    return connectionError('permission_denied', '当前用户无权执行 Tailscale 操作，请检查本机 Tailscale 的管理权限后重试。');
  }
  if (/unknown (?:command|flag)|flag provided but not defined|unrecognized (?:command|option)/i.test(detail)) {
    return connectionError('cli_unsupported', '当前 Tailscale 版本不支持所需的共享命令，请更新 Tailscale 后重试。');
  }
  if (error.killed || error.code === 'ETIMEDOUT') {
    return connectionError('cli_timeout', 'Tailscale 操作超时，请检查 Tailscale 服务后重试；若首次开启共享，请先在 Tailscale 管理后台启用 HTTPS Certificates。');
  }
  if (/failed to connect to local tailscaled|tailscale service is not running|connection refused|cannot connect to.*tailscale/i.test(detail)) {
    return connectionError('daemon_unavailable', '无法连接本机 Tailscale 服务，请启动或重启 Tailscale 后重试。');
  }
  const phase = args[0] !== 'serve' ? '无法读取本机 Tailscale 状态' : args[1] === 'status'
    ? 'Tailscale 已连接，但无法读取 HTTPS 共享配置' : 'Tailscale 已连接，但更新 HTTPS 共享配置失败';
  return connectionError(args[0] !== 'serve' ? 'status_failed' : 'serve_failed', phase + '，请检查 Tailscale 服务后重试。');
}

function createRemoteConnection({ statePath, getTarget, isReady, run = async (file, args) => {
  const result = await runFile(file, args, { timeout: 15000, maxBuffer: 2 * 1024 * 1024, windowsHide: true });
  return result.stdout;
}, platform = process.platform, env = process.env }) {
  let busy = false;
  let cli;
  const read = () => { try { return JSON.parse(fs.readFileSync(statePath, 'utf8')); } catch { return {}; } };
  const save = (value) => fs.writeFileSync(statePath, JSON.stringify(value), { mode: 0o600 });
  async function command(args) {
    const windowsRoots = [env.ProgramW6432, env.ProgramFiles, env['ProgramFiles(x86)'], 'C:\\Program Files'].filter(Boolean);
    const discovered = platform === 'darwin' ? ['/Applications/Tailscale.app/Contents/MacOS/Tailscale', '/usr/local/bin/tailscale', '/opt/homebrew/bin/tailscale', 'tailscale'] : platform === 'win32'
      ? [...windowsRoots.map(root => path.win32.join(root, 'Tailscale', 'tailscale.exe')), 'tailscale.exe'] : ['tailscale', '/usr/bin/tailscale'];
    const candidates = [...new Set([cli, ...discovered].filter(Boolean))];
    for (const candidate of candidates) {
      try { const result = await run(candidate, args); cli = candidate; return result; }
      catch (error) {
        if (error.code !== 'ENOENT') throw commandError(error, args);
        if (cli === candidate) cli = undefined;
      }
    }
    throw connectionError('cli_unavailable', '未找到 Tailscale 命令行程序。若已安装，请完全退出并重新打开 Texa；仍失败时请修复 Tailscale 安装。');
  }
  function parseStatus(output, serve = false) {
    try {
      const value = JSON.parse(output);
      // A new installation can legitimately have no Serve configuration.
      if (serve && value === null) return {};
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
      return value;
    } catch {
      throw connectionError(serve ? 'serve_invalid' : 'status_invalid', serve
        ? 'Tailscale 已连接，但共享配置返回格式异常，请更新 Tailscale 后重试。'
        : 'Tailscale 状态返回格式异常，请更新 Tailscale 后重试。');
    }
  }
  async function inspect() {
    const node = parseStatus(await command(['status', '--json']));
    if (node.BackendState === 'NeedsLogin' || node.BackendState === 'NoState') throw connectionError('login_required', '本机 Tailscale 尚未登录，请在 Tailscale 中完成登录后重试。');
    if (node.BackendState !== 'Running') throw connectionError('daemon_not_running', '本机 Tailscale 尚未连接，请在 Tailscale 中开启连接后重试。');
    const dns = String(node.Self?.DNSName || '').replace(/\.$/, '');
    if (!/^[a-zA-Z0-9.-]+\.ts\.net$/.test(dns)) throw connectionError('dns_unavailable', 'Tailscale 已连接，但尚未取得安全连接地址，请检查 Tailscale 的 MagicDNS 设置后重试。');
    const config = parseStatus(await command(['serve', 'status', '--json']), true);
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
    } catch (error) { return { ...base, error_code: error.code || 'connection_unavailable', message: error.code ? error.message : '无法解析 Tailscale 共享配置，请更新 Tailscale 后重试。' }; }
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
      if (result.error_code) throw connectionError(result.error_code, result.message);
      if (result.enabled !== enabled) throw new Error('连接状态尚未确认，请刷新后检查。');
      return result;
    } finally { busy = false; }
  }
  return { status, setEnabled, restore: async () => { if (read().enabled) return setEnabled(true); } };
}
module.exports = { createRemoteConnection };
