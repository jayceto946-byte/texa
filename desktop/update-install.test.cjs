const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { readFileSync } = fs;
const vm = require('node:vm');
const { EventEmitter } = require('node:events');
const { NsisUpdater } = require('electron-updater');

function fixture(overrides = {}) {
  const calls = [];
  const handlers = new Map();
  const application = new EventEmitter();
  application.relaunch = () => calls.push('relaunch');
  application.quit = () => { calls.push('quit'); application.emit('quit'); };
  const context = {
    updateState: { status: 'downloaded', updateInfo: { version: '1.0.1' } }, updateInstallPromise: null,
    buildIdentity: null, refreshDownloadedUpdate: require('./update-preflight.cjs').refreshDownloadedUpdate,
    sourceUpdater: null, shuttingDown: false, allowQuit: false,
    process: { platform: 'win32' }, backendProcess: null, mainWindow: null,
    fs,
    startBackend: async () => calls.push('started'),
    waitForBackend: async () => true,
    loadAppUrl: async () => calls.push('loaded'),
    desktopAppUrl: url => url, FRONTEND_DEV_URL: '', backendUrl: 'http://127.0.0.1:8000',
    requireLocalRenderer: event => { assert.equal(event.local, true); },
    prepareWindowClose: async () => { calls.push('saved'); return true; },
    stopBackend: async () => { calls.push('stopped'); },
    appendBackendLog: () => {},
    autoUpdater: { installerPath: __filename, checkForUpdates: async () => ({ updateInfo: { version: '1.0.1' } }),
      quitAndInstall: (...args) => calls.push(['install', ...args]) },
    emitUpdateState: state => (context.updateState = { ...context.updateState, ...state }),
    app: application,
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
  assert.equal(f.context.updateState.status, 'installing', 'shutdown progress is visible while waiting');
  finishStopping();
  assert.equal((await first).status, 'installing');
  assert.deepEqual(f.calls, ['saved', 'stopping', 'quit', ['install', true, true]]);
  assert.equal(f.context.allowQuit, true);
});

test('Windows does not spawn the installer until Electron has closed its windows', async () => {
  const application = new EventEmitter();
  application.quit = () => {};
  const f = fixture({ app: application });
  await f.install();
  assert.deepEqual(f.calls, ['saved', 'stopped']);
  application.emit('will-quit');
  assert.deepEqual(f.calls, ['saved', 'stopped']);
  application.emit('quit');
  application.emit('quit');
  assert.deepEqual(f.calls, ['saved', 'stopped', ['install', true, true]]);
});

test('a backend that cannot stop leaves the client and update available for retry', async () => {
  const f = fixture({ backendProcess: {}, stopBackend: async () => { throw Error('still running'); } });
  const result = await f.install();
  assert.equal(result.status, 'downloaded');
  assert.match(result.message, /still running/);
  assert.equal(f.context.allowQuit, false);
  assert.equal(f.context.shuttingDown, false);
  assert.deepEqual(f.calls, ['saved']);
});

test('an unavailable downloaded installer requests a new download before closing the client', async () => {
  const f = fixture({ autoUpdater: { installerPath: null, checkForUpdates: async () => ({ updateInfo: { version: '1.0.1' } }) } });
  assert.equal((await f.install()).status, 'available');
  assert.deepEqual(f.calls, []);
});

test('backend shutdown retains a live process instead of allowing an installer to overwrite it', async () => {
  const source = readFileSync(require.resolve('./main.cjs'), 'utf8');
  const start = source.indexOf('function stopBackend() {');
  const end = source.indexOf('\nasync function startBackend()', start);
  for (const exits of [true, false]) {
    const child = { pid: 123, exitCode: null, signalCode: null };
    const context = {
      backendProcess: child, backendShutdownPromise: null,
      appendBackendLog: () => {}, requestBackendShutdown: async () => true,
      waitForProcessExit: async () => exits,
      forceKillProcessTree: async () => {}, process: { platform: 'win32' },
    };
    if (exits) child.exitCode = 0;
    vm.runInNewContext(source.slice(start, end), context);
    if (exits) await context.stopBackend();
    else {
      await assert.rejects(context.stopBackend(), /本地服务尚未退出/);
      assert.equal(context.backendProcess, child);
      assert.equal(context.backendShutdownPromise, null);
    }
  }
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

test('a failed source install restores the service and allows checking/preparing the update again', async () => {
  const f = fixture({ sourceUpdater: { install: async () => { throw Error('merge failed'); } } });
  assert.equal((await f.install()).status, 'error');
  assert.deepEqual(f.calls, ['saved', 'stopped', 'started', 'loaded']);
  assert.equal(f.context.allowQuit, false);
  assert.equal(f.context.shuttingDown, false);
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
  const f = fixture({ autoUpdater: { installerPath: __filename, checkForUpdates: async () => ({ updateInfo: { version: '1.0.1' } }), quitAndInstall: (silent, reopen) => {
    assert.equal(updater.install(silent, reopen), true);
  } } });
  await f.install();
  assert.equal(spawns.length, 1);
  assert.equal(spawns[0].file, executable);
  assert.deepEqual(spawns[0].args, ['--updated', '/S', '--force-run']);
  assert.equal(updater.disableDifferentialDownload, false, 'differential downloads retain the library default');
});

test('a cached older update is replaced before drafts, backend or windows close', async () => {
  const f = fixture({ autoUpdater: { installerPath: __filename,
    checkForUpdates: async () => ({ updateInfo: { version: '1.0.3' } }),
    downloadUpdate: async () => { f.calls.push('downloaded-latest'); },
    quitAndInstall: () => f.calls.push('installed-latest'),
  } });
  await f.install();
  assert.deepEqual(f.calls, ['downloaded-latest', 'saved', 'stopped', 'quit', 'installed-latest']);
  assert.equal(f.context.updateState.updateInfo.version, '1.0.3');
});

test('failed latest-version check or download leaves the application running', async () => {
  for (const downloadFails of [false, true]) {
    const f = fixture({ autoUpdater: {
      checkForUpdates: async () => {
        if (!downloadFails) throw Error('offline');
        return { updateInfo: { version: '1.0.3' } };
      },
      downloadUpdate: async () => { throw Error('download interrupted'); },
    } });
    await f.install();
    assert.deepEqual(f.calls, []);
    assert.equal(f.context.allowQuit, false);
    assert.equal(f.context.updateState.status, downloadFails ? 'available' : 'downloaded');
  }
});
