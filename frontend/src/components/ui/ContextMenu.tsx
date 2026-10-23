import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

type MenuItem = { label: string; icon?: ReactNode; disabled?: boolean; danger?: boolean; title?: string; onSelect: () => void };

export default function ContextMenu({ x, y, label, trigger, items, onClose }: {
  x: number; y: number; label: string; trigger: HTMLElement; items: MenuItem[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const menu = ref.current;
    if (!menu) return;
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(x, innerWidth - rect.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, innerHeight - rect.height - 8))}px`;
    (menu.querySelector<HTMLButtonElement>('button:not(:disabled)') || menu).focus({ preventScroll: true });
    const dismiss = () => onClose();
    const outside = (event: PointerEvent) => { if (!menu.contains(event.target as Node)) onClose(); };
    // A scroll that brought the row into view can still be queued when this
    // menu opens. Dismiss only after an actual subsequent ancestor movement.
    const scrollPositions = new Map<EventTarget, { top: number; left: number }>();
    for (let parent = trigger.parentElement; parent; parent = parent.parentElement) {
      scrollPositions.set(parent, { top: parent.scrollTop, left: parent.scrollLeft });
    }
    scrollPositions.set(document, { top: window.scrollY, left: window.scrollX });
    const scroll = (event: Event) => {
      if (!event.target) return;
      const initial = scrollPositions.get(event.target);
      if (!initial) return;
      const top = event.target instanceof Element ? event.target.scrollTop : window.scrollY;
      const left = event.target instanceof Element ? event.target.scrollLeft : window.scrollX;
      if (top !== initial.top || left !== initial.left) onClose();
    };
    document.addEventListener('pointerdown', outside, true);
    window.addEventListener('resize', dismiss);
    window.addEventListener('scroll', scroll, true);
    return () => {
      document.removeEventListener('pointerdown', outside, true);
      window.removeEventListener('resize', dismiss);
      window.removeEventListener('scroll', scroll, true);
    };
  }, [x, y, trigger, onClose]);

  return createPortal(<div ref={ref} className="library-context-menu" role="menu" aria-label={label} tabIndex={-1}
    style={{ left: x, top: y }} onContextMenu={event => event.preventDefault()}
    onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose(); trigger.focus(); return; }
      if (event.key === 'Tab') { onClose(); trigger.focus(); return; }
      const buttons = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || []);
      if (!buttons.length || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next].focus();
    }}>
    {items.map(item => <button key={item.label} type="button" role="menuitem" disabled={item.disabled} title={item.title}
      className={item.danger ? 'is-danger' : undefined} onClick={() => { onClose(); trigger.focus(); item.onSelect(); }}>
      {item.icon}<span>{item.label}</span>
    </button>)}
  </div>, document.body);
}
