import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { MoreHorizontal } from 'lucide-react';

/** A small portaled menu; domain commands remain owned by the caller. */
export default function OverflowMenu({ label, children }: { label: string; children: (close: () => void) => ReactNode }) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = () => { setPosition(null); document.getElementById(`${id}-trigger`)?.focus(); };
  useEffect(() => {
    if (!position) return;
    (menu.current?.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)') || menu.current)?.focus();
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setPosition(null);
    };
    // Scroll dismisses instead of leaving a detached menu at the old row position.
    const scroll = (event: Event) => { if (!menu.current?.contains(event.target as Node)) setPosition(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); setPosition(null); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('scroll', scroll, true);
    document.addEventListener('keydown', escape);
    window.addEventListener('resize', scroll);
    return () => { document.removeEventListener('pointerdown', outside, true); document.removeEventListener('scroll', scroll, true); document.removeEventListener('keydown', escape); window.removeEventListener('resize', scroll); };
  }, [position]);
  return <><button ref={trigger} id={`${id}-trigger`} type="button" className="app-icon-button workspace-overflow-trigger" aria-label={label} title={label} aria-haspopup="menu" aria-expanded={Boolean(position)} aria-controls={position ? id : undefined} onClick={() => {
    if (position) { close(); return; }
    const rect = trigger.current!.getBoundingClientRect();
    setPosition({ top: Math.min(rect.bottom + 4, window.innerHeight - 180), left: Math.max(8, Math.min(rect.right - 200, window.innerWidth - 208)) });
  }}><MoreHorizontal size={16} aria-hidden="true" /></button>{position && createPortal(<div ref={menu} id={id} role="menu" tabIndex={-1} aria-label={label} className="workspace-overflow-menu" style={position} onKeyDown={event => {
    const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') || []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (!items.length && event.key !== 'Tab') return;
    let next: number | undefined;
    if (event.key === 'ArrowDown') next = (index + 1) % items.length;
    if (event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = items.length - 1;
    if (next !== undefined) { event.preventDefault(); items[next]?.focus(); }
    if (event.key === 'Tab') { setPosition(null); trigger.current?.focus(); }
  }}>{children(close)}</div>, document.body)}</>;
}
