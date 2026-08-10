const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('kaoyanDesktop', {
  isElectron: true,
  minimize: () => ipcRenderer.invoke('window:minimize'),
  isMaximized: () => ipcRenderer.invoke('window:is-maximized'),
  toggleMaximize: () => ipcRenderer.invoke('window:toggle-maximize'),
  close: () => ipcRenderer.invoke('window:close'),
  onMaximizedChange: (handler) => {
    const listener = (_event, isMaximized) => handler(Boolean(isMaximized));
    ipcRenderer.on('window:maximized-changed', listener);
    return () => ipcRenderer.removeListener('window:maximized-changed', listener);
  },
  restart: () => ipcRenderer.invoke('app:restart'),
  retryStartup: () => ipcRenderer.invoke('startup:retry'),
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
