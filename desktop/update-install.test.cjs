const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { NsisUpdater } = require('electron-updater');

function fixture(overrides = {}) {
  const calls = [];
  const handlers = new Map();
  const context = {
    updateState: { status: 'downloaded' }, updateInstallPromise: null,
    sourceUpdater: null, shuttingDown: false, allowQuit: false,
    requireLocalRenderer: event => { assert.equal(event.local, true); },
    prepareWindowClose: async () => { calls.push('saved'); return true; },
    stopBackend: async () => { calls.push('stopped'); },
    appendBackendLog: () => {},
    autoUpdater: { quitAndInstall: (...args) => calls.push(['install', ...args]) },
    emitUpdateState: state => (context.updateState = { ...context.updateState, ...state }),
    app: { relaunch: () => calls.push('relaunch'), quit: () => calls.push('quit') },
    ipcMain: { handle: (name, handler) => handlers.set(name, handler) },
    ...overrides,
  };
  // Execute the production install function and IPC handler, including their guards.
  const source = readFileSync(require.resolve('./main.cjs'), 'utf8');
  const start = source.indexOf('async function installAppUpdate(event) {');
  const end = source.indexOf('\nif (hasSingleInstanceLock)', start);
  assert.ok(start > 0 && end > start);
  vm.runInNewContext(source.slice(start, end), context);
  return { context, calls, install: () => handlers.get('updates:install')({ local: true }), handlers };
}

test('restart update waits for saved drafts and backend exit, then silently updates and reopens', async () => {
  let finishStopping;
  const f = fixture({ stopBackend: () => {
    f.calls.push('stopping');
    return new Promise(resolve => { finishStopping = resolve; });
  } });
  const first = f.install();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(f.calls, ['saved', 'stopping']);
  assert.equal(f.install(), first, 'concurrent install requests coalesce');
  assert.equal(f.context.allowQuit, false);
  finishStopping();
  assert.equal((await first).status, 'installing');
  assert.deepEqual(f.calls, ['saved', 'stopping', ['install', true, true]]);
  assert.equal(f.context.allowQuit, true);
});

test('only an approved close handshake can override a late renderer unload veto', () => {
  const source = readFileSync(require.resolve('./main.cjs'), 'utf8');
  const start = source.indexOf('function allowPreparedWindowUnload(event) {');
  const end = source.indexOf('\n// Keep the pre-Texa', start);
  assert.ok(start > 0 && end > start);
  assert.match(source, /webContents\.on\('will-prevent-unload', allowPreparedWindowUnload\)/);
  for (const [allowQuit, allowWindowClose, expected] of [
    [false, false, 0], [true, false, 1], [false, true, 1],
  ]) {
    let permitted = 0;
    const context = { allowQuit, allowWindowClose, appendBackendLog: () => {} };
    vm.runInNewContext(source.slice(start, end), context);
    context.allowPreparedWindowUnload({ preventDefault: () => permitted++ });
    assert.equal(permitted, expected);
  }
});

test('incomplete downloads and unsaved drafts cannot start installation or stop the backend', async () => {
  for (const overrides of [
    { updateState: { status: 'downloading' } },
    { prepareWindowClose: async () => false },
  ]) {
    const f = fixture(overrides);
    await f.install();
    assert.deepEqual(f.calls, []);
    assert.equal(f.context.allowQuit, false);
    assert.equal(f.context.shuttingDown, false);
  }
});

test('nonlocal IPC callers cannot install an update', () => {
  const f = fixture();
  assert.throws(() => f.handlers.get('updates:install')({ local: false }));
  assert.deepEqual(f.calls, []);
});

test('source checkouts still use their staged source update and relaunch', async () => {
  let sourceInstalls = 0;
  const f = fixture({ sourceUpdater: { install: async () => { sourceInstalls++; return { status: 'installing' }; } } });
  assert.equal((await f.install()).status, 'installing');
  assert.equal(sourceInstalls, 1);
  assert.deepEqual(f.calls, ['saved', 'stopped', 'relaunch', 'quit']);
});

test('the installed updater translates the production flags to NSIS silent update and restart', async () => {
  const updater = new NsisUpdater(null, { version: '1.0.0', name: 'Texa', isPackaged: true });
  updater.logger = { info() {}, warn() {}, error() {}, debug() {} };
  updater.on('error', error => { throw error; });
  const executable = 'C:\\Temp\\Texa Update.exe';
  updater.downloadedUpdateHelper = { file: executable, downloadedFileInfo: {}, packageFile: null };
  const spawns = [];
  updater.spawnLog = async (file, args) => { spawns.push({ file, args }); return true; };
  // Keep the real install -> doInstall implementation; suppress quitting the test host.
  const f = fixture({ autoUpdater: { quitAndInstall: (silent, reopen) => {
    assert.equal(updater.install(silent, reopen), true);
  } } });
  await f.install();
  assert.equal(spawns.length, 1);
  assert.equal(spawns[0].file, executable);
  assert.deepEqual(spawns[0].args, ['--updated', '/S', '--force-run']);
  assert.equal(updater.disableDifferentialDownload, false, 'differential downloads retain the library default');
});
