const { app, BrowserWindow, ipcMain, shell } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const os = require('node:os');

const BACKEND_PORT = Number(process.env.KAOYAN_BACKEND_PORT || 8000);
const BACKEND_URL = process.env.KAOYAN_BACKEND_URL || `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_DEV_URL = process.env.KAOYAN_FRONTEND_DEV_URL || '';
const API_TOKEN = process.env.KAOYAN_API_TOKEN || crypto.randomBytes(32).toString('hex');
const CAPTURE_TOKEN = process.env.KAOYAN_CAPTURE_TOKEN || crypto.randomBytes(24).toString('hex');
const INSTANCE_ID = process.env.KAOYAN_INSTANCE_ID || crypto.randomUUID();
const SKIP_BACKEND = process.env.KAOYAN_SKIP_BACKEND === '1';

let mainWindow = null;
let backendProcess = null;
let backendStartError = null;
let shuttingDown = false;
let allowQuit = false;
let backendShutdownPromise = null;
let restartingBackend = false;
let updaterConfigured = false;
let updateState = {
  status: 'idle',
  message: '尚未检查更新',
  currentVersion: app.getVersion(),
  updateInfo: null,
  progress: null,
};

function projectRoot() {
  return path.resolve(__dirname, '..');
}

function packagedBackendPath() {
  return path.join(process.resourcesPath, 'backend', 'backend_server', 'backend_server.exe');
}

function runtimePaths() {
  const userData = app.getPath('userData');
  const logDir = path.join(userData, 'logs');
  return {
    userData,
    logDir,
    backendLogPath: path.join(logDir, 'backend.log'),
    dataDir: path.join(userData, 'data'),
    envPath: path.join(userData, '.env'),
    mineruOutputPath: path.join(userData, 'mineru_output'),
  };
}

function remoteCaptureSettingsPath() {
  return path.join(runtimePaths().userData, 'remote-capture.json');
}

function readRemoteCaptureSettings() {
  try {
    const parsed = JSON.parse(fs.readFileSync(remoteCaptureSettingsPath(), 'utf8'));
    return { enabled: parsed?.enabled === true };
  } catch {
    return { enabled: false };
  }
}

function writeRemoteCaptureSettings(enabled) {
  const settingsPath = remoteCaptureSettingsPath();
  fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
  fs.writeFileSync(settingsPath, JSON.stringify({ enabled: Boolean(enabled) }, null, 2), 'utf8');
}

function lanAddresses() {
  const addresses = [];
  for (const entries of Object.values(os.networkInterfaces())) {
    for (const entry of entries || []) {
      if (entry.family !== 'IPv4' || entry.internal) continue;
      if (!addresses.includes(entry.address)) addresses.push(entry.address);
    }
  }
  return addresses;
}

function remoteCaptureStatus(extra = {}) {
  const enabled = readRemoteCaptureSettings().enabled;
  const urls = enabled
    ? lanAddresses().map((address) => `http://${address}:${BACKEND_PORT}/capture#capture_token=${encodeURIComponent(CAPTURE_TOKEN)}`)
    : [];
  return {
    enabled,
    urls,
    port: BACKEND_PORT,
    ready: Boolean(backendProcess && backendProcess.exitCode === null),
    message: enabled
      ? (urls.length ? '\u624b\u673a\u91c7\u96c6\u5165\u53e3\u5df2\u5728\u5f53\u524d\u5c40\u57df\u7f51\u5f00\u653e\u3002' : '\u5df2\u5f00\u653e\uff0c\u4f46\u6ca1\u6709\u627e\u5230\u53ef\u7528\u7684\u5c40\u57df\u7f51 IPv4 \u5730\u5740\u3002')
      : '\u624b\u673a\u91c7\u96c6\u5165\u53e3\u5f53\u524d\u5173\u95ed\u3002',
    ...extra,
  };
}

function appendBackendLog(message) {
  const paths = runtimePaths();
  fs.mkdirSync(paths.logDir, { recursive: true });
  fs.appendFileSync(paths.backendLogPath, `${new Date().toISOString()} ${message}\n`, 'utf8');
}

function backendEnv() {
  const paths = runtimePaths();
  fs.mkdirSync(paths.dataDir, { recursive: true });
  fs.mkdirSync(paths.mineruOutputPath, { recursive: true });

  return {
    ...process.env,
    KAOYAN_BACKEND_PORT: String(BACKEND_PORT),
    KAOYAN_API_TOKEN: API_TOKEN,
    KAOYAN_REQUIRE_API_TOKEN: '1',
    KAOYAN_INSTANCE_ID: INSTANCE_ID,
    KAOYAN_CAPTURE_TOKEN: CAPTURE_TOKEN,
    KAOYAN_BACKEND_HOST: readRemoteCaptureSettings().enabled ? '0.0.0.0' : '127.0.0.1',
    DATA_DIR: paths.dataDir,
    ENV_PATH: paths.envPath,
    MINERU_OUTPUT_PATH: paths.mineruOutputPath,
    SKIP_VECTOR_WARMUP: process.env.SKIP_VECTOR_WARMUP || '0',
    SKIP_EMBEDDING_WARMUP: process.env.SKIP_EMBEDDING_WARMUP || '0',
    EMBEDDING_LOCAL_FILES_ONLY: process.env.EMBEDDING_LOCAL_FILES_ONLY || '1',
  };
}

function loadUpdateConfig() {
  const configPath = path.join(__dirname, 'update-config.json');
  let config = {};
  try {
    if (fs.existsSync(configPath)) {
      config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    }
  } catch (error) {
    console.error('[updater] failed to read update-config.json', error);
  }

  const owner = process.env.KAOYAN_UPDATE_OWNER || config.owner;
  const repo = process.env.KAOYAN_UPDATE_REPO || config.repo;
  const provider = process.env.KAOYAN_UPDATE_PROVIDER || config.provider || 'github';
  const releaseType = process.env.KAOYAN_UPDATE_RELEASE_TYPE || config.releaseType || 'release';

  if (!owner || !repo || owner === 'YOUR_GITHUB_OWNER' || repo === 'YOUR_GITHUB_REPO') {
    return null;
  }

  return { provider, owner, repo, releaseType };
}

function emitUpdateState(nextState) {
  updateState = { ...updateState, ...nextState, currentVersion: app.getVersion() };
  mainWindow?.webContents.send('updates:status', updateState);
  return updateState;
}

function configureUpdater() {
  if (updaterConfigured) return true;

  if (!app.isPackaged && process.env.KAOYAN_ALLOW_DEV_UPDATES !== '1') {
    emitUpdateState({
      status: 'disabled',
      message: '开发模式不执行自动更新。打包后的安装版会启用 GitHub Releases 更新。',
    });
    return false;
  }

  const updateConfig = loadUpdateConfig();
  if (!updateConfig) {
    emitUpdateState({
      status: 'disabled',
      message: '尚未配置 GitHub 更新仓库，请修改 desktop/update-config.json 的 owner/repo。',
    });
    return false;
  }

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.setFeedURL(updateConfig);

  autoUpdater.on('checking-for-update', () => emitUpdateState({ status: 'checking', message: '正在检查更新...', progress: null }));
  autoUpdater.on('update-available', (info) => emitUpdateState({ status: 'available', message: `发现新版本 ${info.version || ''}`.trim(), updateInfo: info, progress: null }));
  autoUpdater.on('update-not-available', (info) => emitUpdateState({ status: 'none', message: '当前已经是最新版本', updateInfo: info, progress: null }));
  autoUpdater.on('download-progress', (progress) => emitUpdateState({ status: 'downloading', message: `正在下载更新 ${Math.round(progress.percent || 0)}%`, progress }));
  autoUpdater.on('update-downloaded', (info) => emitUpdateState({ status: 'downloaded', message: '更新已下载，重启后安装', updateInfo: info, progress: null }));
  autoUpdater.on('error', (error) => emitUpdateState({ status: 'error', message: `更新失败：${error.message || error}`, progress: null }));

  updaterConfigured = true;
  return true;
}

function sendStartupError(message) {
  backendStartError = message;
  mainWindow?.webContents.send('startup-error', startupInfo(message));
}

function startupInfo(message = backendStartError) {
  const paths = runtimePaths();
  return {
    message: message || '',
    backendUrl: BACKEND_URL,
    logPath: paths.backendLogPath,
    dataDir: paths.dataDir,
  };
}

function attachBackendLogging() {
  if (!backendProcess) return;
  backendProcess.stdout?.on('data', (chunk) => appendBackendLog(`[stdout] ${chunk.toString().trimEnd()}`));
  backendProcess.stderr?.on('data', (chunk) => appendBackendLog(`[stderr] ${chunk.toString().trimEnd()}`));
  backendProcess.on('error', (error) => {
    const message = `后端进程启动失败：${error.message || error}`;
    appendBackendLog(`[error] ${message}`);
    sendStartupError(message);
  });
  backendProcess.on('exit', (code, signal) => {
    const message = `后端进程退出：code=${code ?? 'null'}, signal=${signal ?? 'null'}`;
    appendBackendLog(`[exit] ${message}`);
    if (!shuttingDown && !restartingBackend) sendStartupError(message);
  });
}

function waitForProcessExit(child, timeoutMs) {
  if (!child || child.exitCode !== null) return Promise.resolve(true);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (exited) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.removeListener('exit', onExit);
      resolve(exited);
    };
    const onExit = () => finish(true);
    const timer = setTimeout(() => finish(false), timeoutMs);
    child.once('exit', onExit);
  });
}

function forceKillProcessTree(pid) {
  if (!pid) return Promise.resolve();
  if (process.platform === 'win32') {
    return new Promise((resolve) => {
      const killer = spawn('taskkill.exe', ['/pid', String(pid), '/t', '/f'], {
        windowsHide: true,
        stdio: 'ignore',
      });
      killer.once('error', (error) => {
        appendBackendLog('[shutdown] taskkill failed: ' + (error.message || error));
        resolve();
      });
      killer.once('exit', () => resolve());
    });
  }
  try {
    process.kill(-pid, 'SIGKILL');
  } catch (error) {
    if (error?.code !== 'ESRCH') appendBackendLog('[shutdown] force kill failed: ' + (error.message || error));
  }
  return Promise.resolve();
}

function stopBackend() {
  if (backendShutdownPromise) return backendShutdownPromise;
  const child = backendProcess;
  if (!child || child.exitCode !== null) return Promise.resolve();

  backendShutdownPromise = (async () => {
    const pid = child.pid;
    appendBackendLog('[shutdown] stopping backend tree pid=' + pid);
    if (process.platform === 'win32') {
      await forceKillProcessTree(pid);
      await waitForProcessExit(child, 2500);
    } else {
      try {
        child.kill();
      } catch (error) {
        appendBackendLog('[shutdown] graceful stop failed: ' + (error.message || error));
      }
      if (!(await waitForProcessExit(child, 2500))) {
        appendBackendLog('[shutdown] forcing backend tree pid=' + pid);
        await forceKillProcessTree(pid);
        await waitForProcessExit(child, 2500);
      }
    }
    if (backendProcess === child) backendProcess = null;
  })().finally(() => {
    backendShutdownPromise = null;
  });
  return backendShutdownPromise;
}

function startBackend() {
  if (SKIP_BACKEND) {
    appendBackendLog('[main] KAOYAN_SKIP_BACKEND=1, backend spawn skipped.');
    return;
  }

  try {
    const env = backendEnv();
    const backendHost = env.KAOYAN_BACKEND_HOST;
    if (app.isPackaged) {
      const executable = packagedBackendPath();
      appendBackendLog(`[main] starting packaged backend: ${executable}`);
      if (!fs.existsSync(executable)) {
        sendStartupError(`找不到后端可执行文件：${executable}`);
        return;
      }
      backendProcess = spawn(executable, [], {
        cwd: path.dirname(executable),
        windowsHide: true,
        detached: process.platform !== 'win32',
        env,
      });
      attachBackendLogging();
      return;
    }

    const python = process.env.KAOYAN_PYTHON || path.join(projectRoot(), 'venv310', 'Scripts', 'python.exe');
    appendBackendLog(`[main] starting dev backend: ${python}`);
    backendProcess = spawn(
      python,
      ['-m', 'uvicorn', 'backend.main:app', '--host', backendHost, '--port', String(BACKEND_PORT)],
      {
        cwd: projectRoot(),
        windowsHide: true,
        detached: process.platform !== 'win32',
        env,
      },
    );
    attachBackendLogging();
  } catch (error) {
    const message = `后端启动准备失败：${error.message || error}`;
    appendBackendLog(`[error] ${message}`);
    sendStartupError(message);
  }
}

async function waitForBackend(timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  let lastIdentityError = '';
  while (Date.now() < deadline) {
    if (backendStartError) return false;
    if (!SKIP_BACKEND && backendProcess && backendProcess.exitCode !== null) return false;
    try {
      const res = await fetchWithTimeout(`${BACKEND_URL}/health`);
      if (res.ok) {
        const health = await res.json();
        if (SKIP_BACKEND || health?.instance_id === INSTANCE_ID) return true;
        const identityError = `backend identity mismatch at ${BACKEND_URL}`;
        if (identityError !== lastIdentityError) {
          appendBackendLog(`[wait] ${identityError}`);
          lastIdentityError = identityError;
        }
      }
    } catch (error) {
      if (error?.name !== 'AbortError') {
        appendBackendLog(`[wait] backend not ready: ${error.message || error}`);
      } else {
        appendBackendLog(`[wait] backend health check timed out: ${BACKEND_URL}/health`);
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 600));
  }
  return false;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, timeoutMs = 2500) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

function desktopAppUrl(targetUrl) {
  const target = new URL(targetUrl);
  target.searchParams.set('desktop_launch', String(Date.now()));
  const hash = new URLSearchParams(target.hash.replace(/^#/, ''));
  hash.set('access_token', API_TOKEN);
  target.hash = hash.toString();
  return target.toString();
}

async function loadAppUrl(targetUrl) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    await mainWindow.webContents.executeJavaScript("document.body.classList.add('is-leaving')", true);
    await delay(180);
  } catch {
    // The loading document may already be gone; continue into the app.
  }
  if (!mainWindow || mainWindow.isDestroyed() || shuttingDown) return;
  await mainWindow.loadURL(targetUrl);
}

async function openAppWhenBackendReady(timeoutMs = 60000) {
  const ready = await waitForBackend(timeoutMs);
  if (shuttingDown || !mainWindow || mainWindow.isDestroyed()) {
    return { ready: false, message: '应用正在关闭' };
  }
  if (ready) {
    await loadAppUrl(desktopAppUrl(FRONTEND_DEV_URL || BACKEND_URL));
    return { ready: true };
  }

  const message = backendStartError || `后端服务启动超时：${BACKEND_URL}`;
  appendBackendLog(`[timeout] ${message}`);
  sendStartupError(message);
  return { ready: false, message };
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 720,
    minHeight: 560,
    frame: false,
    show: false,
    backgroundColor: '#f5f5f7',
    title: '考研智能辅助系统',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.on('maximize', () => mainWindow?.webContents.send('window:maximized-changed', true));
  mainWindow.on('unmaximize', () => mainWindow?.webContents.send('window:maximized-changed', false));
  mainWindow.loadFile(path.join(__dirname, 'loading.html'));
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const allowedOrigins = [BACKEND_URL, FRONTEND_DEV_URL].filter(Boolean).map((item) => new URL(item).origin);
    if (!allowedOrigins.includes(new URL(url).origin)) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    }
  });

  void openAppWhenBackendReady();
}

ipcMain.handle('window:minimize', () => mainWindow?.minimize());
ipcMain.handle('window:is-maximized', () => mainWindow?.isMaximized() ?? false);
ipcMain.handle('window:toggle-maximize', () => {
  if (!mainWindow) return false;
  const nextState = !mainWindow.isMaximized();
  if (nextState) mainWindow.maximize();
  else mainWindow.unmaximize();
  return nextState;
});
ipcMain.handle('window:close', () => mainWindow?.close());
ipcMain.handle('app:restart', async () => {
  shuttingDown = true;
  await stopBackend();
  allowQuit = true;
  app.relaunch();
  app.quit();
  return true;
});

ipcMain.handle('startup:info', () => startupInfo());
ipcMain.handle('startup:retry', async () => {
  backendStartError = null;
  if (!backendProcess || backendProcess.exitCode !== null) {
    backendProcess = null;
    startBackend();
  }
  return openAppWhenBackendReady();
});
ipcMain.handle('startup:open-web', async () => shell.openExternal(desktopAppUrl(BACKEND_URL)));
ipcMain.handle('startup:open-log', async () => {
  const logPath = runtimePaths().backendLogPath;
  fs.mkdirSync(path.dirname(logPath), { recursive: true });
  if (!fs.existsSync(logPath)) fs.writeFileSync(logPath, '', 'utf8');
  return shell.openPath(logPath);
});

ipcMain.handle('updates:status', () => updateState);
ipcMain.handle('remote-capture:status', () => remoteCaptureStatus());
ipcMain.handle('remote-capture:set-enabled', async (_event, enabled) => {
  writeRemoteCaptureSettings(enabled);
  restartingBackend = true;
  try {
    await stopBackend();
    backendStartError = null;
    startBackend();
    const ready = await waitForBackend(30000);
    return remoteCaptureStatus({
      ready,
      message: ready
        ? (enabled ? '\u624b\u673a\u91c7\u96c6\u5165\u53e3\u5df2\u5f00\u542f\u3002' : '\u624b\u673a\u91c7\u96c6\u5165\u53e3\u5df2\u5173\u95ed\u3002')
        : '\u540e\u7aef\u91cd\u542f\u5931\u8d25\uff0c\u8bf7\u67e5\u770b\u540e\u7aef\u65e5\u5fd7\u3002',
    });
  } finally {
    restartingBackend = false;
  }
});


ipcMain.handle('updates:check', async () => {
  if (!configureUpdater()) return updateState;
  await autoUpdater.checkForUpdates();
  return updateState;
});
ipcMain.handle('updates:download', async () => {
  if (!configureUpdater()) return updateState;
  emitUpdateState({ status: 'downloading', message: '正在下载更新...', progress: null });
  await autoUpdater.downloadUpdate();
  return updateState;
});
ipcMain.handle('updates:install', async () => {
  if (updateState.status !== 'downloaded') {
    return emitUpdateState({ status: 'error', message: '更新尚未下载完成，无法安装。' });
  }
  shuttingDown = true;
  await stopBackend();
  allowQuit = true;
  autoUpdater.quitAndInstall(false, true);
  return emitUpdateState({ status: 'installing', message: '正在重启并安装更新...' });
});

app.whenReady().then(() => {
  startBackend();
  configureUpdater();
  createWindow();
});

app.on('before-quit', (event) => {
  shuttingDown = true;
  if (allowQuit) return;
  event.preventDefault();
  void stopBackend().finally(() => {
    allowQuit = true;
    app.quit();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
