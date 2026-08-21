export {};

type DesktopUpdateStatus = {
  status: 'idle' | 'disabled' | 'checking' | 'available' | 'none' | 'downloading' | 'downloaded' | 'installing' | 'error';
  message: string;
  currentVersion?: string;
  updateInfo?: { version?: string; releaseName?: string; releaseNotes?: string } | null;
  progress?: { percent?: number; transferred?: number; total?: number } | null;
};

type RemoteCaptureStatus = {
  enabled: boolean;
  urls: string[];
  port: number;
  ready: boolean;
  message: string;
};

export type DesktopBackendStatus = {
  status: 'starting' | 'ready' | 'recovering' | 'failed' | 'stopped';
  message: string;
  attempt?: number;
  maxAttempts?: number;
  backendUrl?: string;
  logPath?: string;
  canRetry?: boolean;
};

declare global {
  interface Window {
    kaoyanDesktop?: {
      isElectron: boolean;
      platform?: 'win32' | 'darwin' | 'linux' | string;
      minimize: () => Promise<void>;
      isMaximized?: () => Promise<boolean>;
      toggleMaximize: () => Promise<boolean>;
      close: () => Promise<void>;
      onMaximizedChange?: (handler: (isMaximized: boolean) => void) => () => void;
      restart?: () => Promise<boolean>;
      retryStartup?: () => Promise<{ ready: boolean; message?: string }>;
      getStartupInfo?: () => Promise<{ message?: string; backendUrl?: string; logPath?: string; dataDir?: string }>;
      getBackendStatus?: () => Promise<DesktopBackendStatus>;
      openWebFallback?: () => Promise<void>;
      openBackendLog?: () => Promise<string>;
      getRemoteCaptureStatus?: () => Promise<RemoteCaptureStatus>;
      setRemoteCaptureEnabled?: (enabled: boolean) => Promise<RemoteCaptureStatus>;
      getUpdateStatus?: () => Promise<DesktopUpdateStatus>;
      checkForUpdates?: () => Promise<DesktopUpdateStatus>;
      downloadUpdate?: () => Promise<DesktopUpdateStatus>;
      installUpdate?: () => Promise<DesktopUpdateStatus>;
      onUpdateStatus?: (handler: (status: DesktopUpdateStatus) => void) => () => void;
      onStartupError?: (handler: (payload: { message?: string; backendUrl?: string; logPath?: string } | string) => void) => () => void;
      onBackendStatus?: (handler: (status: DesktopBackendStatus) => void) => () => void;
    };
  }
}
