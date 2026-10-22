export {};

type DesktopUpdateStatus = {
  status: 'idle' | 'disabled' | 'checking' | 'available' | 'none' | 'downloading' | 'downloaded' | 'installing' | 'error';
  message: string;
  currentVersion?: string;
  mode?: 'source' | 'release';
  currentCommit?: string;
  branch?: string;
  updateInfo?: { sourceCommit?: string; sourceBranch?: string; version?: string; releaseName?: string; releaseNotes?: string } | null;
  progress?: { percent?: number; transferred?: number; total?: number } | null;
};

type RemoteCaptureStatus = {
  enabled: boolean;
  urls: string[];
  port: number;
  ready: boolean;
  message: string;
};

export type DesktopRemoteConnection = { ready: boolean; enabled: boolean; url: string; message: string; target: string; error_code?: string };

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
      getSetupComplete?: () => Promise<boolean>;
      setSetupComplete?: () => Promise<boolean>;
      getStartupAppearance?: () => { id: string; tokens: Record<string, string> } | null;
      setStartupAppearance?: (appearance: { id: string; tokens: Record<string, string> }) => Promise<boolean>;
      minimize: () => Promise<void>;
      isFullScreen?: () => Promise<boolean>;
      onFullScreenChange?: (handler: (fullScreen: boolean) => void) => () => void;
      isMaximized?: () => Promise<boolean>;
      toggleMaximize: () => Promise<boolean>;
      close: () => Promise<void>;
      onFocusPower?: (handler: (state: 'suspend' | 'resume') => void) => () => void;
      onPrepareClose?: (handler: (aborted?: boolean) => Promise<boolean>) => () => void;
      onMaximizedChange?: (handler: (isMaximized: boolean) => void) => () => void;
      restart?: () => Promise<boolean>;
      retryStartup?: () => Promise<{ ready: boolean; message?: string }>;
      getStartupInfo?: () => Promise<{ message?: string; backendUrl?: string; logPath?: string; dataDir?: string }>;
      getBackendStatus?: () => Promise<DesktopBackendStatus>;
      openWebFallback?: () => Promise<void>;
      openBackendLog?: () => Promise<string>;
      getRemoteS0Status?: () => Promise<DesktopRemoteConnection>;
      setRemoteConnectionEnabled?: (enabled: boolean) => Promise<DesktopRemoteConnection>;
      copyRemoteConnectionUrl?: () => Promise<boolean>;
      copyRemoteS0Token?: () => Promise<boolean>;
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
