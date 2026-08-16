import { X } from 'lucide-react';
import { useInspector } from '../../contexts/InspectorContext';

export default function ContextInspector() {
  const { inspector, closeInspector } = useInspector();
  if (!inspector) return null;

  return (
    <aside className="context-inspector" aria-label={`${inspector.title}详情`}>
      <header className="context-inspector-header">
        <div className="min-w-0 flex-1">
          {inspector.subtitle && <div className="type-micro text-text-secondary">{inspector.subtitle}</div>}
          <h2 className="mt-0.5 truncate text-[15px] font-semibold text-text-primary">{inspector.title}</h2>
        </div>
        <button type="button" onClick={closeInspector} className="app-icon-button" aria-label="关闭详情面板">
          <X className="h-4 w-4" />
        </button>
      </header>
      <div className="context-inspector-body">{inspector.content}</div>
    </aside>
  );
}
