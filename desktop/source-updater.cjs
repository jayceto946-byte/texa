const fs = require('node:fs/promises');
const path = require('node:path');
const { execFile, execFileSync } = require('node:child_process');
const { promisify } = require('node:util');
const execute = promisify(execFile);
const run = (file, args, options = {}) => execute(file, args, { windowsHide: true, ...options });

/** Source checkouts only. Never stashes, resets, switches branch or installs dependencies. */
function createSourceUpdater({ root, branch = 'Texa_MacOS', owner, repo, node = process.execPath, emit = () => {}, build, allowLocalRemote = false }) {
  let bootCommit = '';
  try { bootCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8', timeout: 5000, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { /* check() reports unavailable git */ }
  let state = { mode: 'source', branch, status: 'idle', message: '按分支提交检查修复', currentCommit: bootCommit, updateInfo: null };
  let busy = false;
  let prepared = null;
  const git = async (...args) => (await run('git', args, { cwd: root, timeout: 60000, maxBuffer: 2 * 1024 * 1024, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } })).stdout.trim();
  const report = next => { state = { ...state, ...next }; emit(state); return { ...state }; };
  const exclusive = async fn => {
    if (busy) return { ...state };
    busy = true;
    try { return await fn(); }
    catch (error) { return report({ status: 'error', message: error.publicMessage || '提交更新失败。请检查网络、Git 权限或源码是否可构建，本地改动不会自动覆盖。' }); }
    finally { busy = false; }
  };
  const fail = message => { const error = new Error(message); error.publicMessage = message; throw error; };
  async function validate() {
    if (await fs.realpath(await git('rev-parse', '--show-toplevel')) !== await fs.realpath(root)) fail('当前路径不是 Texa 主工作区，不能自动更新。');
    if (await git('branch', '--show-current') !== branch) fail(`请先在主工作区切回 ${branch}，不会自动切换分支。`);
    const remote = await git('remote', 'get-url', 'origin');
    const expected = [`git@github.com:${owner}/${repo}.git`, `https://github.com/${owner}/${repo}.git`, `https://github.com/${owner}/${repo}`];
    if (!expected.includes(remote) && !(allowLocalRemote && path.isAbsolute(remote))) fail('origin 与配置的 Texa 仓库不一致，已停止更新。');
    return git('rev-parse', 'HEAD');
  }
  async function clean() {
    if (await git('status', '--porcelain', '--untracked-files=normal')) fail('本地有未提交或未跟踪的文件，请先提交或移出工作区后再更新；不会自动覆盖或暂存它们。');
  }
  async function check() {
    return exclusive(async () => {
      report({ status: 'checking', message: '正在检查分支最新提交…', updateInfo: null });
      const current = await validate();
      if (bootCommit && current !== bootCommit) fail('源码提交已由其他进程改变，请先重启 Texa 后重新检查。');
      report({ currentCommit: current });
      await git('fetch', '--no-tags', 'origin', `refs/heads/${branch}:refs/remotes/origin/${branch}`);
      const target = await git('rev-parse', `refs/remotes/origin/${branch}`);
      if (current === target) return report({ status: 'none', message: await git('status', '--porcelain', '--untracked-files=normal') ? '当前提交已是分支最新；工作区另有本地改动，尚未包含在提交中。' : '当前源码已是分支最新提交' });
      try { await git('merge-base', '--is-ancestor', current, target); }
      catch { fail('本地与远端提交已分叉，需人工合并；不会自动重置本地代码。'); }
      const files = (await git('diff', '--name-only', current, target)).split('\n');
      if (files.some(name => /(^|\/)(package(?:-lock)?\.json|requirements[^/]*|pyproject\.toml|.*\.lock|.*\.db|.*\.sqlite3?)$/.test(name) || /^(data|assets\/embedding-runtime|migrations)\//.test(name) || /(^|\/)(migrations?|schemas?)(\/|\.)/.test(name))) fail('此提交包含依赖、数据或运行环境变更，需要完整升级或人工处理，不能直接拉取修复。');
      report({ updateInfo: { version: target.slice(0, 8), sourceCommit: target, sourceBranch: branch, releaseNotes: await git('log', '-10', '--format=%h %s', `${current}..${target}`) } });
      await clean();
      return report({ status: 'available', message: `发现修复 ${target.slice(0, 8)}，可准备更新` });
    });
  }
  async function prepare() {
    return exclusive(async () => {
      if (state.status !== 'available' || !state.updateInfo) fail('请先检查可用提交。');
      await clean();
      if (await validate() !== state.currentCommit) fail('本地提交已变化，请重新检查更新。');
      report({ status: 'downloading', message: '正在验证修复并构建界面…' });
      if (prepared) await fs.rm(prepared.directory, { recursive: true, force: true });
      const gitDir = await git('rev-parse', '--absolute-git-dir');
      const directory = await fs.mkdtemp(path.join(gitDir, 'texa-update-'));
      prepared = { directory, target: state.updateInfo.sourceCommit, current: state.currentCommit };
      try {
        const archive = path.join(directory, 'source.tar');
        await git('archive', '--format=tar', `--output=${archive}`, prepared.target);
        await run('tar', ['-xf', archive, '-C', directory], { timeout: 60000 });
        if (build) await build(directory);
        else {
          await fs.symlink(path.join(root, 'frontend', 'node_modules'), path.join(directory, 'frontend', 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir');
          for (const args of [['node_modules/typescript/bin/tsc', '-b'], ['node_modules/vite/bin/vite.js', 'build']]) {
            await run(node, args, { cwd: path.join(directory, 'frontend'), timeout: 180000, maxBuffer: 4 * 1024 * 1024, env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' } });
          }
          if (await fs.stat(path.join(directory, 'backend')).then(() => true, () => false)) {
            const python = path.join(root, 'venv310', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
            try { await run(python, ['-c', 'import sys; assert sys.version_info[:2] == (3, 10)'], { timeout: 10000 }); }
            catch { fail('Python 3.10 运行环境不可用，未应用修复。'); }
            const sources = [];
            for (const name of ['backend', 'graph', 'llm', 'memory', 'knowledge', 'ingestion', 'utils', 'config.py', 'main.py']) {
              if (await fs.stat(path.join(directory, name)).then(() => true, () => false)) sources.push(name);
            }
            try { await run(python, ['-m', 'compileall', '-q', ...sources], { cwd: directory, timeout: 60000, maxBuffer: 4 * 1024 * 1024 }); }
            catch { fail('候选 Python 代码未通过编译检查，未应用修复。'); }
          }
        }
        await fs.access(path.join(directory, 'frontend', 'dist', 'index.html'));
        return report({ status: 'downloaded', message: '修复构建通过，可应用并重启' });
      } catch (error) {
        await fs.rm(directory, { recursive: true, force: true }); prepared = null;
        throw error;
      }
    });
  }
  async function install() {
    return exclusive(async () => {
      if (state.status !== 'downloaded' || !prepared) fail('修复尚未准备完成。');
      await clean();
      if (await validate() !== prepared.current) fail('本地提交已变化，请重新检查更新。');
      // The desktop owner stops the backend and fences drafts before calling install.
      const dist = path.join(root, 'frontend', 'dist');
      const previous = path.join(prepared.directory, 'previous-dist');
      const candidate = path.join(prepared.directory, 'frontend', 'dist');
      let moved = false;
      let installed = false;
      try {
        try { await fs.rename(dist, previous); moved = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
        await fs.rename(candidate, dist); installed = true;
        // Swap artifacts first while the backend is stopped. A failed fast-forward
        // restores artifacts without ever resetting the user's Git history.
        await git('merge', '--ff-only', '--no-overwrite-ignore', prepared.target);
      }
      catch (error) {
        if (installed) await fs.rename(dist, candidate);
        if (moved) await fs.rename(previous, dist);
        throw error;
      }
      await fs.rm(prepared.directory, { recursive: true, force: true }).catch(() => {}); prepared = null;
      return report({ status: 'installing', message: '修复已应用，正在重启…' });
    });
  }
  return { check, prepare, install, status: () => ({ ...state }) };
}
module.exports = { createSourceUpdater };
