import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { MoreHorizontal } from 'lucide-react';

export default function ComposerOverflowMenu({
  children, label = '更多', className = '',
}: {
  children: (close: () => void) => ReactNode;
  label?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const openAtEnd = useRef(false);
  const menuId = useId();

  const menuItems = () => Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>(
    '[role="menuitem"]:not(:disabled):not([aria-disabled="true"])',
  ) || []);

  const close = () => {
    setOpen(false);
    document.getElementById(`${menuId}-trigger`)?.focus({ preventScroll: true });
  };

  useEffect(() => {
    if (!open) return;

    const items = menuItems();
    (items[openAtEnd.current ? items.length - 1 : 0] || menuRef.current)?.focus({ preventScroll: true });

    const dismissOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const dismissWithEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus({ preventScroll: true });
    };

    document.addEventListener('pointerdown', dismissOutside, true);
    document.addEventListener('keydown', dismissWithEscape);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside, true);
      document.removeEventListener('keydown', dismissWithEscape);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`chat-more-actions relative ${className}`} onBlur={event => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
    }}>
      <button
        ref={triggerRef}
        id={`${menuId}-trigger`}
        type="button"
        className={`composer-tool-button composer-more-trigger ${open ? 'is-active' : ''}`}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        title={label}
        onClick={() => { openAtEnd.current = false; setOpen((value) => !value); }}
        onKeyDown={event => {
          if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
          event.preventDefault();
          openAtEnd.current = event.key === 'ArrowUp';
          setOpen(true);
        }}
      >
        <MoreHorizontal className="h-4 w-4" aria-hidden="true" /><span>{label}</span>
      </button>
      {open && (
        <div ref={menuRef} id={menuId} className="composer-overflow-menu" role="menu" aria-label={label} tabIndex={-1} onKeyDown={event => {
          if (event.key === 'Tab') { close(); return; }
          const items = menuItems();
          if (!items.length) return;
          const index = items.indexOf(document.activeElement as HTMLButtonElement);
          let next: number | undefined;
          if (event.key === 'ArrowDown') next = (index + 1) % items.length;
          if (event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length;
          if (event.key === 'Home') next = 0;
          if (event.key === 'End') next = items.length - 1;
          if (next !== undefined) { event.preventDefault(); items[next]?.focus({ preventScroll: true }); }
        }}>
          {children(close)}
        </div>
      )}
    </div>
  );
}
