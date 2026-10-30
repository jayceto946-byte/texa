import { TexaClose } from '../icons';
import { useEffect, useRef, useState } from 'react';

import { useInspector } from '../../contexts/InspectorContext';
import Dialog from './Dialog';

export default function ContextInspector() {
  const { inspector, closeInspector } = useInspector();
  const panelRef = useRef<HTMLElement | null>(null);
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 919.98px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 919.98px)');
    const change = () => setNarrow(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  const open = Boolean(inspector);
  useEffect(() => {
    if (!open || narrow) return;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = requestAnimationFrame(() => panelRef.current?.querySelector<HTMLButtonElement>('button')?.focus());
    return () => {
      cancelAnimationFrame(frame);
      requestAnimationFrame(() => { if (trigger?.isConnected && !trigger.closest('[hidden]')) trigger.focus(); });
    };
  }, [open, narrow]);
  if (!inspector) return null;
  const content = <><header className="context-inspector-header">
    <div className="min-w-0 flex-1">
      {inspector.subtitle && <div className="type-micro text-text-secondary">{inspector.subtitle}</div>}
      <h2 className="mt-0.5 truncate text-[15px] font-semibold text-text-primary">{inspector.title}</h2>
    </div>
    <button type="button" onClick={closeInspector} className="app-icon-button context-inspector-close" aria-label="关闭详情面板"><TexaClose className="h-4 w-4" /></button>
  </header><div className="context-inspector-body">{inspector.content}</div></>;
  return narrow ? <Dialog open title={`${inspector.title}详情`} onClose={closeInspector} dismissOnBackdrop className="context-inspector-modal">{content}</Dialog>
    : <aside ref={panelRef} className="context-inspector" aria-label={`${inspector.title}详情`}>{content}</aside>;
}
