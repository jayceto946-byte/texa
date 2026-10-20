const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { existsSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { createSourceUpdater } = require('./source-updater.cjs');

async function fixture(t, { dependency = false, brokenBuild = false, realBuild = false, badPython = false } = {}) {
  const base = await fs.mkdtemp(path.join(os.tmpdir(), 'texa-source-update-test-'));
  t.after(() => fs.rm(base, { recursive: true, force: true }));
  const upstream = path.join(base, 'upstream'); const root = path.join(base, 'local');
  await fs.mkdir(upstream);
  const git = (dir, ...args) => execFileSync('git', args, { cwd: dir, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  git(upstream, 'init', '-b', 'Texa_MacOS');
  git(upstream, 'config', 'user.email', 'test@example.invalid'); git(upstream, 'config', 'user.name', 'Fixture');
  await fs.writeFile(path.join(upstream, 'fix.txt'), 'before');
  await fs.mkdir(path.join(upstream, 'frontend'));
  await fs.writeFile(path.join(upstream, 'frontend', '.gitignore'), 'dist/\nnode_modules\n');
  await fs.writeFile(path.join(upstream, 'frontend', 'index.html'), '<script type="module" src="/main.ts"></script>');
  await fs.writeFile(path.join(upstream, 'frontend', 'main.ts'), 'document.body.textContent = "Built candidate";');
  await fs.writeFile(path.join(upstream, 'frontend', 'tsconfig.json'), '{"compilerOptions":{"target":"ES2022","module":"ESNext","skipLibCheck":true},"include":["main.ts"]}');
  git(upstream, 'add', '.'); git(upstream, 'commit', '-m', 'before');
  git(base, 'clone', upstream, root);
  const previous = git(root, 'rev-parse', 'HEAD');
  await fs.writeFile(path.join(upstream, dependency ? 'requirements.txt' : 'fix.txt'), 'after');
  if (badPython) {
    await fs.mkdir(path.join(upstream, 'backend'));
    await fs.writeFile(path.join(upstream, 'backend', 'broken.py'), 'def broken(:\n');
    await fs.writeFile(path.join(root, '.git', 'info', 'exclude'), 'venv310\n');
    await fs.symlink(path.resolve(__dirname, '../venv310'), path.join(root, 'venv310'), process.platform === 'win32' ? 'junction' : 'dir');
  }
  git(upstream, 'add', '.'); git(upstream, 'commit', '-m', 'fix');
  const target = git(upstream, 'rev-parse', 'HEAD');
  if (realBuild) await fs.symlink(path.resolve(__dirname, '../frontend/node_modules'), path.join(root, 'frontend', 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir');
  const updater = createSourceUpdater({ root, owner: 'owner', repo: 'repo', allowLocalRemote: true, build: realBuild ? undefined : async directory => {
    if (brokenBuild) throw new Error('build failed');
    await fs.mkdir(path.join(directory, 'frontend', 'dist'), { recursive: true });
    await fs.writeFile(path.join(directory, 'frontend', 'dist', 'index.html'), 'new UI');
  } });
  return { updater, root, upstream, previous, target, git };
}
test('stages and builds before a fast-forward, then swaps only compiled assets', async t => {
  const f = await fixture(t);
  assert.equal((await f.updater.check()).status, 'available');
  assert.equal((await f.updater.prepare()).status, 'downloaded');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
  assert.equal((await f.updater.install()).status, 'installing');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.target);
  assert.equal(await fs.readFile(path.join(f.root, 'frontend', 'dist', 'index.html'), 'utf8'), 'new UI');
});
test('dirty files are preserved and block updates', async t => {
  const f = await fixture(t); await fs.writeFile(path.join(f.root, 'fix.txt'), 'private work');
  assert.equal((await f.updater.check()).status, 'error');
  assert.equal(await fs.readFile(path.join(f.root, 'fix.txt'), 'utf8'), 'private work');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
});
test('dependency changes require explicit full upgrade', async t => {
  const f = await fixture(t, { dependency: true });
  assert.equal((await f.updater.check()).status, 'error');
  assert.match(f.updater.status().message, /依赖/);
});
test('failed candidate build leaves the running checkout intact', async t => {
  const f = await fixture(t, { brokenBuild: true }); await f.updater.check();
  assert.equal((await f.updater.prepare()).status, 'error');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
});
test('new local work after preparation blocks install', async t => {
  const f = await fixture(t); await f.updater.check(); await f.updater.prepare();
  await fs.writeFile(path.join(f.root, 'new-note.txt'), 'keep');
  assert.equal((await f.updater.install()).status, 'error');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
});
test('divergent local commits are not reset or merged automatically', async t => {
  const f = await fixture(t);
  f.git(f.root, 'config', 'user.email', 'test@example.invalid'); f.git(f.root, 'config', 'user.name', 'Fixture');
  await fs.writeFile(path.join(f.root, 'local.txt'), 'keep'); f.git(f.root, 'add', '.'); f.git(f.root, 'commit', '-m', 'local');
  const head = f.git(f.root, 'rev-parse', 'HEAD');
  assert.equal((await f.updater.check()).status, 'error');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), head);
});
test('asset swap failure preserves the previous source commit and UI', async t => {
  const f = await fixture(t);
  await fs.mkdir(path.join(f.root, 'frontend', 'dist'));
  await fs.writeFile(path.join(f.root, 'frontend', 'dist', 'index.html'), 'old UI');
  await f.updater.check(); await f.updater.prepare();
  const directory = (await fs.readdir(path.join(f.root, '.git'))).find(name => name.startsWith('texa-update-'));
  await fs.mkdir(path.join(f.root, '.git', directory, 'previous-dist'));
  await fs.writeFile(path.join(f.root, '.git', directory, 'previous-dist', 'blocker'), 'block');
  assert.equal((await f.updater.install()).status, 'error');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
  assert.equal(await fs.readFile(path.join(f.root, 'frontend', 'dist', 'index.html'), 'utf8'), 'old UI');
});
test('the real TypeScript/Vite pipeline builds an archived target before updating the checkout', async t => {
  const f = await fixture(t, { realBuild: true });
  assert.equal((await f.updater.check()).status, 'available');
  assert.equal((await f.updater.prepare()).status, 'downloaded');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
  assert.equal((await f.updater.install()).status, 'installing');
  assert.match(await fs.readFile(path.join(f.root, 'frontend', 'dist', 'index.html'), 'utf8'), /assets/);
});
test('a remote tracked file cannot overwrite an ignored local file', async t => {
  const f = await fixture(t);
  await fs.writeFile(path.join(f.root, '.git', 'info', 'exclude'), 'settings.local\n');
  await fs.writeFile(path.join(f.root, 'settings.local'), 'private settings');
  await fs.writeFile(path.join(f.upstream, 'settings.local'), 'remote settings');
  f.git(f.upstream, 'add', '.'); f.git(f.upstream, 'commit', '-m', 'new file');
  await f.updater.check(); await f.updater.prepare();
  assert.equal((await f.updater.install()).status, 'error');
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
  assert.equal(await fs.readFile(path.join(f.root, 'settings.local'), 'utf8'), 'private settings');
});
test('Python syntax failure rejects a candidate without changing the running source', { skip: !existsSync(path.resolve(__dirname, '../venv310', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')) }, async t => {
  const f = await fixture(t, { realBuild: true, badPython: true });
  assert.equal((await f.updater.check()).status, 'available');
  assert.equal((await f.updater.prepare()).status, 'error');
  assert.match(f.updater.status().message, /编译检查/);
  assert.equal(f.git(f.root, 'rev-parse', 'HEAD'), f.previous);
});
