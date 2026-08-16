import { useEffect, useRef, useState, type ReactNode } from 'react';
import { MoreHorizontal } from 'lucide-react';

export default function ComposerOverflowMenu({
  children,
}: {
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    const dismissOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const dismissWithEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    };

    document.addEventListener('pointerdown', dismissOutside, true);
    document.addEventListener('keydown', dismissWithEscape);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside, true);
      document.removeEventListener('keydown', dismissWithEscape);
    };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <div ref={rootRef} className="chat-more-actions relative">
      <button
        ref={triggerRef}
        type="button"
        className={`composer-tool-button composer-more-trigger ${open ? 'is-active' : ''}`}
        aria-label="更多"
        aria-haspopup="menu"
        aria-expanded={open}
        title="更多"
        onClick={() => setOpen((value) => !value)}
      >
        <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
      </button>
      {open && (
        <div className="composer-overflow-menu" role="menu" aria-label="更多学习操作">
          {children(close)}
        </div>
      )}
    </div>
  );
}
