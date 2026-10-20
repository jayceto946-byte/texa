import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { History } from 'lucide-react';
import { LearningHistoryContext } from './learningHistoryContext';
import './LearningHistoryDock.css';

/** Keeps one history list mounted while its presentation changes with navigation. */
export default function LearningHistoryDock({ docked, children }: {
  docked: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const pointerInside = useRef(false);
  const openOverlays = useRef(new Set<string>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = useId();
  const clearClose = useCallback(() => { if (timer.current) clearTimeout(timer.current); timer.current = null; }, []);
  const containsTarget = useCallback((target: EventTarget | null) => target instanceof Node && (
    root.current?.contains(target) || [...openOverlays.current].some(key => document.getElementById(key)?.contains(target))
  ), []);
  const close = useCallback(() => { clearClose(); setOpen(false); }, [clearClose]);
  const scheduleClose = useCallback(() => {
    clearClose();
    timer.current = setTimeout(() => { timer.current = null; if (!pointerInside.current) setOpen(false); }, 180);
  }, [clearClose]);
  const onMenuOpenChange = useCallback((value: boolean, key: string) => {
    const wasOpen = openOverlays.current.has(key);
    if (value) openOverlays.current.add(key);
    else openOverlays.current.delete(key);
    if (openOverlays.current.size) clearClose();
    else if (wasOpen && !pointerInside.current) scheduleClose();
  }, [clearClose, scheduleClose]);
  useEffect(() => {
    if (!docked) { clearClose(); setOpen(false); pointerInside.current = false; }
    return clearClose;
  }, [clearClose, docked]);
  useEffect(() => {
    if (!docked || !open) return;
    const outside = (event: PointerEvent) => {
      if (!containsTarget(event.target)) close();
    };
    const move = (event: PointerEvent) => {
      if (event.pointerType === 'touch') return;
      pointerInside.current = Boolean(containsTarget(event.target));
      if (pointerInside.current) clearClose();
      else if (!timer.current) scheduleClose();
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('pointermove', move);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('pointermove', move); };
  }, [clearClose, close, containsTarget, docked, open, scheduleClose]);

  return <div ref={root} className="learning-history-host" data-docked={docked} data-open={docked && open}
    onPointerEnter={event => { if (docked && event.pointerType !== 'touch') { pointerInside.current = true; clearClose(); setOpen(true); } }}
    onPointerLeave={event => { pointerInside.current = Boolean(containsTarget(event.relatedTarget)); if (docked && !pointerInside.current) scheduleClose(); }}
    onFocusCapture={event => { if (docked && event.target.matches(':focus-visible')) { clearClose(); setOpen(true); } }}
    onBlurCapture={event => { if (docked && !containsTarget(event.relatedTarget)) scheduleClose(); }}
    onKeyDownCapture={event => {
      if (docked && open && event.key === 'Escape' && !openOverlays.current.size) {
        event.preventDefault(); event.stopPropagation(); trigger.current?.focus(); close();
      }
    }}>
    {docked && <button ref={trigger} type="button" className="history-edge-trigger" aria-label="展开对话历史" title="对话历史 · 悬停展开"
      aria-expanded={open} aria-controls={id} onClick={() => { clearClose(); setOpen(true); }}>
      <History size={16} aria-hidden="true" /><span>历史</span>
    </button>}
    <div id={id} className="learning-history-panel" inert={docked && !open}>
      <LearningHistoryContext.Provider value={{ visible: !docked || open, close, onMenuOpenChange }}>{children}</LearningHistoryContext.Provider>
    </div>
  </div>;
}
