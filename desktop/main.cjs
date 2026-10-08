const { app, BrowserWindow, ipcMain, shell, clipboard } = require('electron');
const { autoUpdater } = require('electron-updater');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { backendIdentityMatches, findAvailablePort, portFromUrl, resolveUserDataPath } = require('./runtime.cjs');
const { readStartupAppearance, writeStartupAppearance } = require('./appearance.cjs');
const { createClosePreparation } = require('./window-close.cjs');
const { readSetupComplete, writeSetupComplete } = require('./setup-state.cjs');
const closePreparation = createClosePreparation();
let allowWindowClose = false;

async function prepareWindowClose() {
  const ready = await closePreparation.prepare(mainWindow?.webContents);
  if (!ready) {
    mainWindow?.webContents.send('window:close-aborted');
    mainWindow?.show();
  }
  return ready;
}

// Keep the pre-Texa userData locations stable. Changing productName/package name
// without this override would make existing installations appear to lose data.
app.setName('Texa');
if (process.platform === 'win32') app.setAppUserModelId('local.kaoyan.assistant');
app.setPath('userData', resolveUserDataPath({
  override: process.env.KAOYAN_USER_DATA_DIR,
  appDataPath: app.getPath('appData'),
  isPackaged: app.isPackaged,
}));
const STARTUP_APPEARANCE_PATH = path.join(app.getPath('userData'), 'startup-appearance.json');
const SETUP_COMPLETE_PATH = path.join(app.getPath('userData'), 'setup-complete.json');
let startupAppearance = readStartupAppearance(STARTUP_APPEARANCE_PATH);
const APP_ICON_PATH = path.join(__dirname, 'assets', 'texa-taskbar.ico');

const BACKEND_URL_OVERRIDE = (process.env.KAOYAN_BACKEND_URL || '').trim();
const BACKEND_PORT_OVERRIDE = Number(process.env.KAOYAN_BACKEND_PORT || 0);
const FRONTEND_DEV_URL = process.env.KAOYAN_FRONTEND_DEV_URL || '';
const API_TOKEN = process.env.KAOYAN_API_TOKEN || crypto.randomBytes(32).toString('hex');
const CAPTURE_TOKEN = process.env.KAOYAN_CAPTURE_TOKEN || crypto.randomBytes(24).toString('hex');
const INSTANCE_ID = process.env.KAOYAN_INSTANCE_ID || crypto.randomUUID();
const SKIP_BACKEND = process.env.KAOYAN_SKIP_BACKEND === '1';
const USE_DYNAMIC_BACKEND_PORT = !SKIP_BACKEND && !BACKEND_URL_OVERRIDE && !BACKEND_PORT_OVERRIDE;
const MAX_BACKEND_RECOVERY_ATTEMPTS = 3;

let backendPort = BACKEND_PORT_OVERRIDE || portFromUrl(BACKEND_URL_OVERRIDE) || 8000;
let backendUrl = BACKEND_URL_OVERRIDE || `http://127.0.0.1:${backendPort}`;

let mainWindow = null;
let backendProcess = null;
let backendStartError = null;
let backendFailure = null;
let lastBackendExit = '';
let shuttingDown = false;
let allowQuit = false;
let backendShutdownPromise = null;
let backendRecoveryPromise = null;
let restartingBackend = false;
let backendState = {
  status: 'starting',
  message: '正在启动本地服务',
  attempt: 0,
  maxAttempts: MAX_BACKEND_RECOVERY_ATTEMPTS,
};
const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) app.quit();
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
  const name = process.platform === 'win32' ? 'backend_server.exe' : 'backend_server';
  return path.join(process.resourcesPath, 'backend', 'backend_server', name);
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

function remoteCaptureStatus(extra = {}) {
  return { enabled: false, urls: [], port: backendPort, ready: false,
    message: 'LAN 采集入口已停用；请使用 Tailscale Serve 连接现有学习页面。', ...extra };

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
    KAOYAN_BACKEND_PORT: String(backendPort),
    KAOYAN_API_TOKEN: API_TOKEN,
    KAOYAN_REQUIRE_API_TOKEN: '1',
    KAOYAN_INSTANCE_ID: INSTANCE_ID,
    KAOYAN_CAPTURE_TOKEN: CAPTURE_TOKEN,
    KAOYAN_BACKEND_HOST: '127.0.0.1',
    DATA_DIR: paths.dataDir,
    ENV_PATH: paths.envPath,
    MINERU_OUTPUT_PATH: paths.mineruOutputPath,
    SKIP_VECTOR_WARMUP: process.env.SKIP_VECTOR_WARMUP || '0',
    SKIP_EMBEDDING_WARMUP: process.env.SKIP_EMBEDDING_WARMUP || '0',
    EMBEDDING_LOCAL_FILES_ONLY: process.env.EMBEDDING_LOCAL_FILES_ONLY || '1',
    TEXA_EMBEDDING_BACKEND: process.env.TEXA_EMBEDDING_BACKEND || 'onnx',
    TEXA_EMBEDDING_ASSET_DIR: process.env.TEXA_EMBEDDING_ASSET_DIR || (
      app.isPackaged
        ? path.join(process.resourcesPath, 'embedding-runtime', 'bge-small-zh-v1.5', 'onnx-fp32-v1')
        : path.join(projectRoot(), 'assets', 'embedding-runtime', 'bge-small-zh-v1.5', 'onnx-fp32-v1')
    ),
    TEXA_REQUIRE_SUPPORTED_ARCH: app.isPackaged ? '1' : (process.env.TEXA_REQUIRE_SUPPORTED_ARCH || '0'),
    TEXA_REQUIRE_WINDOWS_X64: process.platform === 'win32' && app.isPackaged ? '1' : (process.env.TEXA_REQUIRE_WINDOWS_X64 || '0'),
    RERANKER_MODEL_PATH: process.env.RERANKER_MODEL_PATH || '',
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

function sendStartupError(message, failure = null) {
  backendStartError = message;
  backendFailure = failure;
  emitBackendState({ status: 'failed', message, failure, canRetry: true });
  mainWindow?.webContents.send('startup-error', startupInfo(message, failure));
}

function emitBackendState(nextState) {
  backendState = {
    ...backendState,
    ...nextState,
    backendUrl,
    logPath: runtimePaths().backendLogPath,
  };
  mainWindow?.webContents.send('backend:status', backendState);
  return backendState;
}

function startupInfo(message = backendStartError, failure = backendFailure) {
  const paths = runtimePaths();
  return {
    message: message || '',
    backendUrl,
    logPath: paths.backendLogPath,
    dataDir: paths.dataDir,
    failure,
  };
}

function attachBackendLogging() {
  if (!backendProcess) return;
  const child = backendProcess;
  child.stdout?.on('data', (chunk) => appendBackendLog(`[stdout] ${chunk.toString().trimEnd()}`));
  child.stderr?.on('data', (chunk) => appendBackendLog(`[stderr] ${chunk.toString().trimEnd()}`));
  child.on('error', (error) => {
    const message = `后端进程启动失败：${error.message || error}`;
    appendBackendLog(`[error] ${message}`);
    sendStartupError(message);
  });
  child.on('exit', (code, signal) => {
    const message = `后端进程退出：code=${code ?? 'null'}, signal=${signal ?? 'null'}`;
    appendBackendLog(`[exit] ${message}`);
    if (backendProcess === child) backendProcess = null;
    if (shuttingDown || restartingBackend) return;
    lastBackendExit = message;
    if (!SKIP_BACKEND) void recoverBackend(message);
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

async function requestBackendShutdown() {
  try {
    const response = await fetch(`${backendUrl}/api/system/shutdown`, {
      method: 'POST',
      headers: { 'X-Kaoyan-Token': API_TOKEN },
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) {
      appendBackendLog(`[shutdown] graceful endpoint returned HTTP ${response.status}`);
      return false;
    }
    const payload = await response.json();
    appendBackendLog(`[shutdown] graceful shutdown accepted; cancelling_jobs=${payload?.cancelling_jobs || 0}`);
    return payload?.success === true;
  } catch (error) {
    appendBackendLog('[shutdown] graceful endpoint unavailable: ' + (error.message || error));
    return false;
  }
}

async function prepareBackendEndpoint() {
  if (!USE_DYNAMIC_BACKEND_PORT) return;
  const host = '127.0.0.1';
  backendPort = await findAvailablePort(host);
  backendUrl = `http://127.0.0.1:${backendPort}`;
  appendBackendLog(`[main] allocated backend endpoint ${backendUrl} (bind host ${host})`);
}

function stopBackend() {
  if (backendShutdownPromise) return backendShutdownPromise;
  const child = backendProcess;
  if (!child || child.exitCode !== null) return Promise.resolve();

  backendShutdownPromise = (async () => {
    const pid = child.pid;
    appendBackendLog('[shutdown] stopping backend tree pid=' + pid);
    const gracefulRequested = await requestBackendShutdown();
    if (gracefulRequested && await waitForProcessExit(child, 8000)) {
      appendBackendLog('[shutdown] backend exited gracefully');
    } else if (process.platform === 'win32') {
      appendBackendLog('[shutdown] graceful timeout; forcing backend tree pid=' + pid);
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

async function startBackend() {
  if (SKIP_BACKEND) {
    appendBackendLog('[main] KAOYAN_SKIP_BACKEND=1, backend spawn skipped.');
    return;
  }

  try {
    backendFailure = null;
    await prepareBackendEndpoint();
    emitBackendState({ status: 'starting', message: `正在启动本地服务（端口 ${backendPort}）`, canRetry: false });
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

    // A healthy process on the port may belong to an older desktop token.
    // Never present it as this desktop's ready/configured backend.
    const existing = await probeExistingBackend();
    if (existing) {
      if (!backendIdentityMatches(existing, INSTANCE_ID)) {
        sendStartupError(`端口 ${backendPort} 被另一后端实例占用。请完整退出旧 Texa / 本地后端后重试；不会接管旧实例或覆盖配置。`);
        return;
      }
      const authorized = await fetchWithTimeout(`${backendUrl}/api/system/remote-ready`, 2500, {
        headers: { 'X-Kaoyan-Token': API_TOKEN },
      });
      if (!authorized.ok) {
        sendStartupError('端口上的后端与当前桌面访问令牌不匹配，请完整退出旧服务后重试。');
        return;
      }
      appendBackendLog(`[main] dev: using explicitly matching backend at ${backendUrl} (spawn skipped).`);
      lastBackendExit = '';
      return;
    }

    const python = process.env.KAOYAN_PYTHON || (process.platform === 'win32'
      ? path.join(projectRoot(), 'venv310', 'Scripts', 'python.exe')
      : path.join(projectRoot(), 'venv310', 'bin', 'python'));
    appendBackendLog(`[main] starting dev backend: ${python}`);
    lastBackendExit = '';
    backendProcess = spawn(
      python,
      ['-m', 'uvicorn', 'backend.main:app', '--host', backendHost, '--port', String(backendPort)],
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
    if (!SKIP_BACKEND && !backendProcess && lastBackendExit) return false;
    try {
      const res = await fetchWithTimeout(`${backendUrl}/health`);
      if (res.ok) {
        const health = await res.json();
        const identityMatches = backendIdentityMatches(health, INSTANCE_ID, SKIP_BACKEND);
        if (identityMatches) {
          const warmup = health?.warmup || {};
          if (warmup.status === 'ready') return true;
          if (warmup.status === 'error') {
            const failure = warmup.failure || { code: warmup.error || 'EMBEDDING_RUNTIME_FAILURE' };
            const message = failure.message || `Texa runtime preparation failed (${failure.code})`;
            sendStartupError(message, failure);
            return false;
          }
          if (warmup.status === 'degraded') {
            const failure = warmup.failure || { code: warmup.error || 'RETRIEVAL_DEGRADED' };
            const message = failure.message || `Texa retrieval preparation failed (${failure.code})`;
            sendStartupError(message, failure);
            return false;
          }
          emitBackendState({
            status: 'preparing',
            stage: warmup.stage || 'runtime_check',
            message: warmup.message || '正在准备 Texa',
            failure: null,
            canRetry: false,
          });
          await delay(200);
          continue;
        }
        const identityError = `backend identity mismatch at ${backendUrl}`;
        if (identityError !== lastIdentityError) {
          appendBackendLog(`[wait] ${identityError}`);
          lastIdentityError = identityError;
        }
      }
    } catch (error) {
      if (error?.name !== 'AbortError') {
        appendBackendLog(`[wait] backend not ready: ${error.message || error}`);
      } else {
        appendBackendLog(`[wait] backend health check timed out: ${backendUrl}/health`);
      }
    }
    // Dev mode: our spawned backend already exited (e.g. the port was taken) and
    // nothing healthy answers — fail with the recorded exit reason instead of
    // waiting out the full timeout.
    if (!app.isPackaged && !SKIP_BACKEND && backendProcess && backendProcess.exitCode !== null) {
      return false;
    }
    await new Promise((resolve) => setTimeout(resolve, 600));
  }
  return false;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, timeoutMs = 2500, init = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function probeExistingBackend(timeoutMs = 2500) {
  try {
    const res = await fetchWithTimeout(`${backendUrl}/health`, timeoutMs);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

function desktopAppUrl(targetUrl) {
  const target = new URL(targetUrl);
  target.searchParams.set('desktop_launch', String(Date.now()));
  const hash = new URLSearchParams(target.hash.replace(/^#/, ''));
  hash.set('access_token', API_TOKEN);
  hash.set('api_base', `${backendUrl}/api`);
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
    backendFailure = null;
    emitBackendState({ status: 'ready', message: '本地服务已就绪', attempt: 0, canRetry: false });
    await loadAppUrl(desktopAppUrl(FRONTEND_DEV_URL || backendUrl));
    return { ready: true };
  }

  if (backendRecoveryPromise) {
    const recovered = await backendRecoveryPromise;
    if (recovered) return { ready: true };
  }

  // Preserve typed warmup failures so the loading page keeps its repair UI.
  if (backendFailure) {
    return { ready: false, ...startupInfo(backendStartError, backendFailure) };
  }

  const message = backendStartError || lastBackendExit || `后端服务启动超时：${backendUrl}`;
  appendBackendLog(`[timeout] ${message}`);
  sendStartupError(message);
  return { ready: false, message };
}

function recoverBackend(reason) {
  if (backendRecoveryPromise) return backendRecoveryPromise;
  backendRecoveryPromise = (async () => {
    appendBackendLog(`[recovery] starting automatic recovery: ${reason}`);
    for (let attempt = 1; attempt <= MAX_BACKEND_RECOVERY_ATTEMPTS; attempt += 1) {
      if (shuttingDown) return false;
      emitBackendState({
        status: 'recovering',
        message: `本地服务中断，正在自动恢复（${attempt}/${MAX_BACKEND_RECOVERY_ATTEMPTS}）`,
        attempt,
        canRetry: false,
      });
      await delay(Math.min(4000, 500 * (2 ** (attempt - 1))));
      backendStartError = null;
      lastBackendExit = '';
      backendProcess = null;
      await startBackend();
      if (await waitForBackend(30000)) {
        appendBackendLog(`[recovery] backend recovered on attempt ${attempt}`);
        emitBackendState({ status: 'ready', message: '本地服务已恢复', attempt: 0, canRetry: false });
        if (mainWindow && !mainWindow.isDestroyed()) {
          await loadAppUrl(desktopAppUrl(FRONTEND_DEV_URL || backendUrl));
        }
        return true;
      }
      appendBackendLog(`[recovery] attempt ${attempt} failed: ${backendStartError || lastBackendExit || 'health check timeout'}`);
    }
    const message = backendStartError || lastBackendExit || '本地服务自动恢复失败';
    sendStartupError(`${message}；已自动重试 ${MAX_BACKEND_RECOVERY_ATTEMPTS} 次`);
    return false;
  })().finally(() => {
    backendRecoveryPromise = null;
  });
  return backendRecoveryPromise;
}

async function retryBackendManually() {
  if (backendRecoveryPromise) return { ready: await backendRecoveryPromise };
  restartingBackend = true;
  try {
    await stopBackend();
  } finally {
    restartingBackend = false;
  }
  backendStartError = null;
  lastBackendExit = '';
  backendProcess = null;
  const ready = await recoverBackend('用户手动重试');
  return ready ? { ready: true } : { ready: false, message: backendStartError || lastBackendExit || '本地服务恢复失败' };
}

async function repairEmbeddingRuntime() {
  emitBackendState({ status: 'preparing', stage: 'asset_prepare', message: '正在修复 ONNX 模型资源', canRetry: false });
  try {
    const response = await fetch(`${backendUrl}/api/system/assets/repair/embedding`, {
      method: 'POST',
      headers: { 'X-Kaoyan-Token': API_TOKEN, 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(180000),
    });
    const payload = await response.json();
    if (!response.ok || payload?.success !== true) {
      const failure = payload?.error || { code: 'ASSET_REPAIR_FAILED', recoverable: true, repair_action: 'repair_embedding_runtime' };
      sendStartupError(payload?.message || 'ONNX embedding runtime repair failed', failure);
      return startupInfo(payload?.message, failure);
    }
  } catch (error) {
    const failure = {
      code: 'ASSET_REPAIR_FAILED', stage: 'asset_repair', recoverable: true,
      message: error?.message || String(error), repair_action: 'repair_embedding_runtime',
    };
    sendStartupError('ONNX embedding runtime repair failed', failure);
    return startupInfo('ONNX embedding runtime repair failed', failure);
  }
  restartingBackend = true;
  try {
    await stopBackend();
    backendStartError = null;
    backendFailure = null;
    lastBackendExit = '';
    backendProcess = null;
    await startBackend();
    const ready = await waitForBackend(90000);
    if (ready) {
      emitBackendState({ status: 'ready', message: '模型资源已修复', attempt: 0, canRetry: false });
      await loadAppUrl(desktopAppUrl(FRONTEND_DEV_URL || backendUrl));
      return { ready: true };
    }
    return startupInfo();
  } finally {
    restartingBackend = false;
  }
}

function createWindow() {
  allowWindowClose = false;
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 720,
    minHeight: 560,
    ...(process.platform === 'darwin'
      ? { titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 18, y: 11 } }
      : { frame: false }),
    show: false,
    backgroundColor: startupAppearance?.tokens['--color-bg-primary'] || '#faf9f6',
    title: 'Texa',
    icon: APP_ICON_PATH,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.on('close', (event) => {
    if (allowQuit || allowWindowClose) return;
    event.preventDefault();
    void prepareWindowClose().then((ready) => {
      if (ready && mainWindow && !mainWindow.isDestroyed()) {
        allowWindowClose = true;
        mainWindow.close();
      }
    });
  });
  mainWindow.on('maximize', () => mainWindow?.webContents.send('window:maximized-changed', true));
  mainWindow.on('unmaximize', () => mainWindow?.webContents.send('window:maximized-changed', false));
  mainWindow.loadFile(path.join(__dirname, 'loading.html'));
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('blob:')) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          autoHideMenuBar: true,
          webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
        },
      };
    }
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const allowedOrigins = [backendUrl, FRONTEND_DEV_URL].filter(Boolean).map((item) => new URL(item).origin);
    if (!allowedOrigins.includes(new URL(url).origin)) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    }
  });
  mainWindow.webContents.on('did-finish-load', () => emitBackendState({}));

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
ipcMain.on('window:prepared-close', (event, nonce, ready) => {
  closePreparation.acknowledge(event.sender.id, nonce, ready === true);
});
ipcMain.handle('setup:get-complete', (event) => event.sender === mainWindow?.webContents && readSetupComplete(SETUP_COMPLETE_PATH));
ipcMain.handle('setup:set-complete', (event) => event.sender === mainWindow?.webContents && writeSetupComplete(SETUP_COMPLETE_PATH));
ipcMain.on('appearance:get', (event) => { event.returnValue = startupAppearance; });
ipcMain.handle('appearance:set', (_event, value) => {
  const saved = writeStartupAppearance(STARTUP_APPEARANCE_PATH, value);
  if (saved) startupAppearance = saved;
  return Boolean(saved);
});
ipcMain.handle('app:restart', async () => {
  if (!await prepareWindowClose()) return false;
  shuttingDown = true;
  await stopBackend();
  allowQuit = true;
  app.relaunch();
  app.quit();
  return true;
});

ipcMain.handle('startup:info', () => startupInfo());
ipcMain.handle('startup:retry', retryBackendManually);
ipcMain.handle('startup:repair-embedding', repairEmbeddingRuntime);
ipcMain.handle('startup:open-web', async () => shell.openExternal(desktopAppUrl(backendUrl)));
ipcMain.handle('startup:open-log', async () => {
  const logPath = runtimePaths().backendLogPath;
  fs.mkdirSync(path.dirname(logPath), { recursive: true });
  if (!fs.existsSync(logPath)) fs.writeFileSync(logPath, '', 'utf8');
  return shell.openPath(logPath);
});

ipcMain.handle('updates:status', () => updateState);
ipcMain.handle('backend:status', () => emitBackendState({}));
ipcMain.handle('remote-capture:status', () => remoteCaptureStatus());
ipcMain.handle('remote-capture:set-enabled', () => remoteCaptureStatus());
// This IPC is available only to the local desktop renderer, never through HTTP.
ipcMain.handle('remote-s0:status', (event) => {
  if (event.sender !== mainWindow?.webContents) throw new Error('Access denied');
  const ready = !SKIP_BACKEND && backendState.status === 'ready' && Boolean(backendProcess);
  return { ready, target: backendUrl, instanceId: INSTANCE_ID,
    command: `tailscale serve --bg --https=443 http://127.0.0.1:${backendPort}` };
});
ipcMain.handle('remote-s0:copy-token', (event) => {
  if (event.sender !== mainWindow?.webContents || SKIP_BACKEND || backendState.status !== 'ready') return false;
  clipboard.writeText(API_TOKEN);
  return true;
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
  if (!await prepareWindowClose()) return emitUpdateState({ status: 'downloaded', message: '草稿尚未保存，请先处理未保存修改。' });
  shuttingDown = true;
  await stopBackend();
  allowQuit = true;
  autoUpdater.quitAndInstall(false, true);
  return emitUpdateState({ status: 'installing', message: '正在重启并安装更新...' });
});

if (hasSingleInstanceLock) {
  app.on('second-instance', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(async () => {
    appendBackendLog(`[main] runtime: isPackaged=${app.isPackaged}; appPath=${app.getAppPath()}; frontend=${FRONTEND_DEV_URL || (app.isPackaged ? 'bundled backend assets' : path.join(projectRoot(), 'frontend', 'dist'))}`);
    await startBackend();
    configureUpdater();
    createWindow();
  });
}

app.on('before-quit', (event) => {
  if (allowQuit) return;
  event.preventDefault();
  void prepareWindowClose().then(async (ready) => {
    if (!ready) return;
    shuttingDown = true;
    await stopBackend();
    allowQuit = true;
    app.quit();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
