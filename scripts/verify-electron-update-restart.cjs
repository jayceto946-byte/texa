// Real Electron close/relaunch witness. Synthetic page, no user data or installer.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const vm = require('node:vm');
const { spawn } = require('node:child_process');

async function runChild() {
  const { app, BrowserWindow, ipcMain } = require('electron');
  const { NsisUpdater } = require('../desktop/node_modules/electron-updater');
  const { createClosePreparation } = require('../desktop/window-close.cjs');
  const directory = process.env.TEXA_RESTART_WITNESS_DIR;
  const scenario = process.env.TEXA_RESTART_WITNESS_SCENARIO;
  const output = path.join(directory, 'result.json');
  const firstBoot = path.join(directory, 'first-boot.json');
  app.setPath('userData', path.join(directory, 'profile'));
  await app.whenReady();
  if (process.argv.includes('--reopened')) {
    const initial = JSON.parse(fs.readFileSync(firstBoot, 'utf8'));
    fs.writeFileSync(output, JSON.stringify({ ...initial, reopened: true, newPid: process.pid }));
    app.exit(0);
    return;
  }
  const window = new BrowserWindow({ show: false, webPreferences: {
    preload: path.resolve(__dirname, '../desktop/preload.cjs'), contextIsolation: true, sandbox: true,
  } });
  const record = { scenario, oldPid: process.pid, prepared: false, stopped: false,
    installArgs: null, unloadAttempts: 0, reopened: false, messages: [] };
  const write = () => fs.writeFileSync(firstBoot, JSON.stringify(record));
  const source = fs.readFileSync(path.resolve(__dirname, '../desktop/main.cjs'), 'utf8');
  const closePreparation = createClosePreparation({ timeoutMs: 1500 });
  const context = {
    mainWindow: window, closePreparation, allowQuit: false, allowWindowClose: false,
    shuttingDown: false, updateState: { status: 'downloaded' }, updateInstallPromise: null,
    sourceUpdater: null, ipcMain, app,
    appendBackendLog: message => record.messages.push(message),
    requireLocalRenderer: event => { if (event.sender !== window.webContents) throw Error('Access denied'); },
    stopBackend: async () => { record.stopped = true; write(); },
    emitUpdateState: state => (context.updateState = { ...context.updateState, ...state }),
  };
  // Execute the production close preparation, unload guard and install IPC.
  const prepareStart = source.indexOf('async function prepareWindowClose() {');
  const prepareEnd = source.indexOf('\n// Keep the pre-Texa', prepareStart);
  vm.runInNewContext(source.slice(prepareStart, prepareEnd), context);
  const installStart = source.indexOf('async function installAppUpdate(event) {');
  const installEnd = source.indexOf('\nif (hasSingleInstanceLock)', installStart);
  vm.runInNewContext(source.slice(installStart, installEnd), context);
  const quitStart = source.indexOf("app.on('before-quit', (event) => {");
  const quitEnd = source.indexOf("app.on('window-all-closed'", quitStart);
  vm.runInNewContext(source.slice(quitStart, quitEnd), context);
  ipcMain.on('window:prepared-close', (event, nonce, ready) => {
    record.prepared = ready === true;
    closePreparation.acknowledge(event.sender.id, nonce, ready);
    write();
  });
  window.webContents.on('will-prevent-unload', event => {
    record.unloadAttempts++;
    if (scenario !== 'baseline') context.allowPreparedWindowUnload(event);
    write();
  });
  // Retain the real BaseUpdater -> NsisUpdater flag translation and quit event.
  // Substitute only the installer spawn, then relaunch this isolated witness.
  const updater = new NsisUpdater(null, { version: '1.0.0', name: 'Texa-witness', isPackaged: true,
    quit: () => {
      app.once('will-quit', () => app.relaunch({ args: [__filename, '--child', '--reopened'] }));
      app.quit();
    },
  });
  updater.logger = { info() {}, warn() {}, error() {}, debug() {} };
  updater.on('error', error => { record.error = String(error); write(); });
  updater.downloadedUpdateHelper = { file: path.join(directory, 'fixture-installer.exe'), downloadedFileInfo: {}, packageFile: null };
  updater.spawnLog = async (_file, args) => { record.installArgs = args; write(); return true; };
  context.autoUpdater = updater;
  await window.loadURL('data:text/html,<title>Update witness</title><p>Fixture only</p>');
  await window.webContents.executeJavaScript(`
    window.kaoyanDesktop.onPrepareClose(async () => ${scenario !== 'veto'});
    window.addEventListener('beforeunload', event => { event.preventDefault(); event.returnValue = false; });
  `);
  await window.webContents.executeJavaScript('window.kaoyanDesktop.installUpdate()').catch(() => {});
  // An unapproved close must remain open. Baseline reproduces the late veto.
  setTimeout(() => {
    fs.writeFileSync(output, JSON.stringify({ ...record, stillOpen: !window.isDestroyed() }));
    // app.exit bypasses will-quit, so a blocked baseline does not relaunch.
    app.exit(0);
  }, 1800);
}

async function main() {
  const executable = require('../desktop/node_modules/electron');
  const output = process.argv[2] || path.resolve('docs/qa/update-restart-2026-10-23/native.json');
  const results = [];
  for (const scenario of ['baseline', 'fixed', 'veto']) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-restart-witness-'));
    const env = { ...process.env, TEXA_RESTART_WITNESS_DIR: directory, TEXA_RESTART_WITNESS_SCENARIO: scenario };
    delete env.ELECTRON_RUN_AS_NODE;
    const child = spawn(executable, [__filename, '--child'], { env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
    let diagnostics = '';
    child.stderr.on('data', chunk => { diagnostics += chunk.toString(); });
    let launchError;
    child.on('error', error => { launchError = error; });
    try {
      const target = path.join(directory, 'result.json');
      const deadline = Date.now() + 20000;
      while (!fs.existsSync(target) && Date.now() < deadline && !launchError) await new Promise(resolve => setTimeout(resolve, 50));
      if (launchError) throw launchError;
      if (!fs.existsSync(target)) throw Error(`Electron witness timed out (${scenario}): ${diagnostics}`);
      const result = JSON.parse(fs.readFileSync(target, 'utf8'));
      const forceRun = result.installArgs?.join(' ') === '--updated /S --force-run';
      const passed = scenario === 'fixed'
        ? result.prepared && result.stopped && result.unloadAttempts > 0 && result.reopened && result.oldPid !== result.newPid && forceRun
        : scenario === 'baseline' ? result.prepared && result.stopped && result.unloadAttempts > 0 && result.stillOpen && !result.reopened && forceRun
          : !result.prepared && !result.stopped && result.installArgs === null && result.stillOpen && !result.reopened;
      results.push({ ...result, passed: Boolean(passed) });
    } finally {
      // Fixture-only process and profile, never a user's Texa process.
      if (child.exitCode === null) child.kill();
    }
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify({ platform: process.platform,
    scope: 'real Electron renderer/IPC/quit/relaunch; real NSIS flag translation; installer spawn and backend substituted', results }, null, 2) + '\n');
  console.log(JSON.stringify(results.map(({ scenario, passed, reopened }) => ({ scenario, passed, reopened }))));
  if (results.some(result => !result.passed)) process.exitCode = 1;
}

if (process.argv.includes('--child')) runChild().catch(error => { console.error(error); require('electron').app.exit(1); });
else main().catch(error => { console.error(error); process.exitCode = 1; });
