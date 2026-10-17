import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import './help-hint.css';

/** Optional explanation only; consequences and errors belong in the document. */
export function HelpHint({ label, children }: { label: string; children: React.ReactNode }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const pinned = useRef(false);
  useLayoutEffect(() => {
    if (!open || !trigger.current || !popup.current) return;
    const place = () => {
      const a = trigger.current!.getBoundingClientRect(), p = popup.current!.getBoundingClientRect();
      popup.current!.style.left = `${Math.max(8, Math.min(a.left - 8, innerWidth - p.width - 8))}px`;
      popup.current!.style.top = `${Math.max(8, Math.min(a.bottom + 8 + p.height <= innerHeight - 8 ? a.bottom + 8 : a.top - p.height - 8, innerHeight - p.height - 8))}px`;
    };
    place(); window.addEventListener('resize', place); document.addEventListener('scroll', place, true);
    return () => { window.removeEventListener('resize', place); document.removeEventListener('scroll', place, true); };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const close = (e: KeyboardEvent | PointerEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !trigger.current?.contains(e.target as Node) && !popup.current?.contains(e.target as Node)) {
        pinned.current = false; setOpen(false);
      }
    };
    document.addEventListener('keydown', close); document.addEventListener('pointerdown', close);
    return () => { document.removeEventListener('keydown', close); document.removeEventListener('pointerdown', close); };
  }, [open]);
  return <span className="exercise-help">
    <button ref={trigger} type="button" aria-label={`${label}说明`} aria-expanded={open} aria-describedby={open ? id : undefined} onMouseEnter={() => setOpen(true)} onMouseLeave={() => { if (!pinned.current && document.activeElement !== trigger.current) setOpen(false); }} onFocus={() => setOpen(true)} onBlur={() => { if (!pinned.current) setOpen(false); }} onClick={() => { pinned.current = !pinned.current; setOpen(pinned.current); }}>?</button>{open && createPortal(<div ref={popup} role="tooltip" id={id} className="exercise-help-popup">{children}</div>, document.body)}</span>;
}
