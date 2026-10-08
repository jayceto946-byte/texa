const { contextBridge, ipcRenderer } = require('electron');
const closeHandlers = new Set();
ipcRenderer.on('window:prepare-close', async (_event, nonce) => {
  let ready = true;
  for (const handler of closeHandlers) {
    try { if (await handler() !== true) ready = false; }
    catch { ready = false; }
  }
  ipcRenderer.send('window:prepared-close', nonce, ready);
});
ipcRenderer.on('window:close-aborted', () => {
  for (const handler of closeHandlers) void Promise.resolve(handler(true)).catch(() => {});
});

contextBridge.exposeInMainWorld('kaoyanDesktop', {
  isElectron: true,
  getRemoteS0Status: () => ipcRenderer.invoke('remote-s0:status'),
  copyRemoteS0Token: () => ipcRenderer.invoke('remote-s0:copy-token'),
  platform: process.platform,
  getSetupComplete: () => ipcRenderer.invoke('setup:get-complete'),
  setSetupComplete: () => ipcRenderer.invoke('setup:set-complete'),
  getStartupAppearance: () => ipcRenderer.sendSync('appearance:get'),
  setStartupAppearance: (appearance) => ipcRenderer.invoke('appearance:set', appearance),
  minimize: () => ipcRenderer.invoke('window:minimize'),
  isMaximized: () => ipcRenderer.invoke('window:is-maximized'),
  toggleMaximize: () => ipcRenderer.invoke('window:toggle-maximize'),
  close: () => ipcRenderer.invoke('window:close'),
  onPrepareClose: (handler) => {
    closeHandlers.add(handler);
    return () => closeHandlers.delete(handler);
  },
  onMaximizedChange: (handler) => {
    const listener = (_event, isMaximized) => handler(Boolean(isMaximized));
    ipcRenderer.on('window:maximized-changed', listener);
    return () => ipcRenderer.removeListener('window:maximized-changed', listener);
  },
  restart: () => ipcRenderer.invoke('app:restart'),
  retryStartup: () => ipcRenderer.invoke('startup:retry'),
  repairEmbeddingRuntime: () => ipcRenderer.invoke('startup:repair-embedding'),
  getStartupInfo: () => ipcRenderer.invoke('startup:info'),
  getBackendStatus: () => ipcRenderer.invoke('backend:status'),
  openWebFallback: () => ipcRenderer.invoke('startup:open-web'),
  openBackendLog: () => ipcRenderer.invoke('startup:open-log'),
  getRemoteCaptureStatus: () => ipcRenderer.invoke('remote-capture:status'),
  setRemoteCaptureEnabled: (enabled) => ipcRenderer.invoke('remote-capture:set-enabled', Boolean(enabled)),
  getUpdateStatus: () => ipcRenderer.invoke('updates:status'),
  checkForUpdates: () => ipcRenderer.invoke('updates:check'),
  downloadUpdate: () => ipcRenderer.invoke('updates:download'),
  installUpdate: () => ipcRenderer.invoke('updates:install'),
  onUpdateStatus: (handler) => {
    const listener = (_event, status) => handler(status);
    ipcRenderer.on('updates:status', listener);
    return () => ipcRenderer.removeListener('updates:status', listener);
  },
  onStartupError: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on('startup-error', listener);
    return () => ipcRenderer.removeListener('startup-error', listener);
  },
  onBackendStatus: (handler) => {
    const listener = (_event, status) => handler(status);
    ipcRenderer.on('backend:status', listener);
    return () => ipcRenderer.removeListener('backend:status', listener);
  },
});
