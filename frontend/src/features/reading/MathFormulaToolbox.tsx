import { useLayoutEffect, useRef, useState } from 'react';
import { X, Trash2 } from 'lucide-react';
import MathFieldEditor, { type MathFieldEditorHandle } from '../math-input/MathFieldEditor';
import { mathTemplateCategories, mathTemplates, type MathTemplateCategory } from '../math-input/mathTemplates';
import { hasUnfilledPlaceholder, templateToEditorLatex } from '../math-input/formulaEditorUtils';
import './math-formula-toolbox.css';

type Props = {
  anchor: HTMLElement;
  latex: string;
  display: boolean;
  editing: boolean;
  onChange: (latex: string) => void;
  onDisplayChange: (display: boolean) => void;
  onSave: () => void;
  onRemove: () => void;
  onClose: () => void;
};

/** Top-layer placement avoids clipping inside scrolling editors and nested dialogs. */
export function MathFormulaToolbox({ anchor, latex, display, editing, onChange, onDisplayChange, onSave, onRemove, onClose }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const field = useRef<MathFieldEditorHandle>(null);
  const [category, setCategory] = useState<MathTemplateCategory>('common');
  useLayoutEffect(() => {
    const element = panel.current!;
    const position = () => {
      const r = anchor.getBoundingClientRect();
      const size = Math.min(320, innerWidth - 24, innerHeight - 24);
      const above = innerHeight - r.bottom - 8 < size && r.top - 8 >= size;
      element.style.width = `${size}px`;
      element.style.height = `${size}px`;
      element.style.left = `${Math.max(12, Math.min(r.right - size, innerWidth - size - 12))}px`;
      element.style.top = `${Math.max(12, Math.min(above ? r.top - size - 8 : r.bottom + 8, innerHeight - size - 12))}px`;
      element.dataset.side = above ? 'above' : 'below';
    };
    position();
    element.showPopover();
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    return () => {
      element.hidePopover();
      window.removeEventListener('resize', position);
      window.removeEventListener('scroll', position, true);
    };
  }, [anchor]);
  return <div ref={panel} popover="auto" role="dialog" aria-label="数学符号工具箱" className="math-formula-toolbox" onToggle={event => { if (event.newState === 'closed') onClose(); }} onKeyDown={event => {
    if (event.key === 'Escape') { event.stopPropagation(); event.preventDefault(); onClose(); anchor.focus({ preventScroll: true }); }
  }}>
    <header><strong>{editing ? '编辑公式' : '数学符号'}</strong><button type="button" className="app-icon-button" aria-label="关闭数学工具箱" onClick={onClose}><X size={15} /></button></header>
    <div className="math-toolbox-categories" role="tablist" aria-label="符号分类">{mathTemplateCategories.map(item => <button key={item.id} type="button" role="tab" aria-selected={category === item.id} onClick={() => setCategory(item.id)}>{item.label}</button>)}</div>
    <div className="math-toolbox-symbols" role="toolbar" aria-label="数学模板">{mathTemplates.filter(item => item.category === category).map(item => <button key={item.id} type="button" title={item.description} aria-label={item.description} onMouseDown={event => event.preventDefault()} onClick={() => field.current?.insert(templateToEditorLatex(item))}>{item.label}</button>)}</div>
    <MathFieldEditor ref={field} value={latex} onChange={onChange} ariaLabel="可视化编辑公式" autoFocus />
    <footer><label><input type="checkbox" checked={display} onChange={event => onDisplayChange(event.target.checked)} />独立公式</label><div>{editing && <button type="button" className="app-icon-button" aria-label="删除公式" onClick={onRemove}><Trash2 size={15} /></button>}<button type="button" className="app-primary-button" disabled={!latex.trim() || hasUnfilledPlaceholder(latex)} onClick={onSave}>{editing ? '保存' : '插入'}</button></div></footer>
  </div>;
}
