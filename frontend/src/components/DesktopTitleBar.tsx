export default function DesktopTitleBar() {
  if (!window.kaoyanDesktop?.isElectron) return null;

  // Presence marker for Electron-only drag-region and safe-area styles.
  // Window buttons are provided by Electron's native Window Controls Overlay.
  return <div className="desktop-titlebar-marker" aria-hidden="true" />;
}
