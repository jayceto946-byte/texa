import { Copy, Minus, Square, X } from 'lucide-react';
import { useEffect, useState } from 'react';

export default function DesktopTitleBar() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!window.kaoyanDesktop?.isElectron) return;
    window.kaoyanDesktop.isMaximized?.().then(setMaximized).catch(() => undefined);
    return window.kaoyanDesktop.onMaximizedChange?.(setMaximized);
  }, []);

  if (!window.kaoyanDesktop?.isElectron) return null;
  if (window.kaoyanDesktop.platform === 'darwin') return <div className="desktop-titlebar-marker" aria-hidden="true" />;

  return (
    <div className="desktop-titlebar-marker" aria-label="窗口控制">
      <button type="button" onClick={() => void window.kaoyanDesktop?.minimize()} className="desktop-window-button" aria-label="最小化窗口"><Minus /></button>
      <button type="button" onClick={() => void window.kaoyanDesktop?.toggleMaximize().then(setMaximized)} className="desktop-window-button" aria-label={maximized ? '还原窗口' : '最大化窗口'}>{maximized ? <Copy className="desktop-restore-icon" /> : <Square />}</button>
      <button type="button" onClick={() => void window.kaoyanDesktop?.close()} className="desktop-window-button desktop-window-close" aria-label="关闭窗口"><X /></button>
    </div>
  );
}
