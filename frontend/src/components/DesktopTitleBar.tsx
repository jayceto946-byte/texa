import { useEffect, useState } from 'react';
import { Copy, Minus, Square, X } from 'lucide-react';

export default function DesktopTitleBar() {
  const desktop = window.kaoyanDesktop;
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    if (!desktop?.isElectron) return;

    let active = true;
    void desktop.isMaximized?.().then((value) => {
      if (active) setIsMaximized(value);
    });
    const unsubscribe = desktop.onMaximizedChange?.(setIsMaximized);

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, [desktop]);

  if (!desktop?.isElectron) return null;

  const minimize = () => void desktop.minimize();
  const toggleMaximize = () => {
    void desktop.toggleMaximize().then(setIsMaximized);
  };
  const close = () => void desktop.close();

  return (
    <div className="desktop-window-controls" role="group" aria-label="窗口控制">
      <button
        className="desktop-window-control desktop-window-control--minimize"
        type="button"
        aria-label="最小化"
        onClick={minimize}
      >
        <Minus aria-hidden="true" />
      </button>
      <button
        className="desktop-window-control desktop-window-control--maximize"
        type="button"
        aria-label={isMaximized ? '还原' : '最大化'}
        onClick={toggleMaximize}
      >
        {isMaximized ? <Copy aria-hidden="true" /> : <Square aria-hidden="true" />}
      </button>
      <button
        className="desktop-window-control desktop-window-control--close"
        type="button"
        aria-label="关闭"
        onClick={close}
      >
        <X aria-hidden="true" />
      </button>
    </div>
  );
}
