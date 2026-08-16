import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, Grid3X3, Sigma, X } from 'lucide-react';

import { hasUnfilledPlaceholder, templateToEditorLatex } from './formulaEditorUtils';
import MathFieldEditor, { type MathFieldEditorHandle } from './MathFieldEditor';
import MatrixBuilder from './MatrixBuilder';
import { mathQuickKeys } from './mathQuickKeys';
import {
  mathTemplateCategories,
  mathTemplates,
  type MathTemplate,
  type MathTemplateCategory,
} from './mathTemplates';
import type { MathEditRequest } from './types';

type PanelView = 'templates' | 'editor' | 'matrix';

interface VisualMathInputPopoverProps {
  disabled?: boolean;
  editRequest?: MathEditRequest | null;
  onAddExpression: (latex: string, displayMode: boolean) => void;
  onUpdateExpression: (id: string, latex: string, displayMode: boolean) => void;
}

const VisualMathInputPopover: React.FC<VisualMathInputPopoverProps> = ({
  disabled = false,
  editRequest = null,
  onAddExpression,
  onUpdateExpression,
}) => {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<MathTemplateCategory>('common');
  const [view, setView] = useState<PanelView>('templates');
  const [editorLatex, setEditorLatex] = useState('');
  const [displayMode, setDisplayMode] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editorKey, setEditorKey] = useState(0);
  const [matrixSize, setMatrixSize] = useState<[number, number]>([2, 2]);
  const rootRef = useRef<HTMLDivElement>(null);
  const mathFieldRef = useRef<MathFieldEditorHandle>(null);
  const templates = useMemo(
    () => mathTemplates.filter((template) => template.category === category),
    [category],
  );

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (!editRequest) return;
    setOpen(true);
    setView('editor');
    setEditorLatex(editRequest.expression.latex);
    setDisplayMode(editRequest.expression.displayMode);
    setEditingId(editRequest.expression.id);
    setEditorKey((value) => value + 1);
  }, [editRequest]);

  const closePanel = () => {
    setOpen(false);
    setView('templates');
    setEditingId(null);
  };

  const beginFormula = (template: MathTemplate) => {
    if (template.id === 'matrix-2' || template.id === 'matrix-3') {
      const size = template.id === 'matrix-3' ? 3 : 2;
      setMatrixSize([size, size]);
      setEditingId(null);
      setView('matrix');
      return;
    }
    setEditorLatex(templateToEditorLatex(template));
    setDisplayMode(false);
    setEditingId(null);
    setEditorKey((value) => value + 1);
    setView('editor');
  };

  const saveFormula = () => {
    const latex = editorLatex.trim();
    if (!latex || hasUnfilledPlaceholder(latex)) return;
    if (editingId) onUpdateExpression(editingId, latex, displayMode);
    else onAddExpression(latex, displayMode);
    closePanel();
  };

  const saveMatrix = (latex: string) => {
    onAddExpression(latex, true);
    closePanel();
  };

  const editorInvalid = !editorLatex.trim() || hasUnfilledPlaceholder(editorLatex);
  const title = view === 'matrix' ? '矩阵输入' : view === 'editor' ? (editingId ? '编辑公式' : '可视化公式编辑') : '数学符号与公式';
  const helper = view === 'matrix'
    ? '选择行列和外框，再逐格填写矩阵。'
    : view === 'editor'
      ? '直接点击公式中的位置修改，不需要编辑 LaTeX 源码。'
      : '选择模板后，在可视化编辑器中填写。';

  return (
    <div ref={rootRef} className="relative flex-shrink-0">
      <button
        type="button"
        aria-label="打开数学符号面板"
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          setOpen((value) => !value);
          setView('templates');
          setEditingId(null);
        }}
        className={`composer-tool-button ${open ? 'is-active' : ''}`}
        title="数学符号与公式"
      >
        <Sigma className="h-4 w-4" aria-hidden="true" />
        <span>公式</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="数学符号与公式"
          className="math-input-panel fixed bottom-[54px] left-16 right-2 z-30 max-h-[min(72vh,620px)] overflow-hidden rounded-xl border border-border bg-bg-card md:absolute md:bottom-[calc(100%+0.5rem)] md:left-0 md:right-auto md:w-[min(calc(100vw-2rem),680px)]"
        >
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <div className="flex min-w-0 items-center gap-2">
              {view !== 'templates' && (
                <button type="button" aria-label="返回数学模板" onClick={() => { setView('templates'); setEditingId(null); }} className="math-input-back flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-text-secondary hover:bg-[var(--surface-muted)] hover:text-text-primary">
                  <ChevronLeft className="h-4 w-4" />
                </button>
              )}
              <div className="min-w-0">
                <div className="type-control text-text-primary">{title}</div>
                <div className="truncate type-caption text-text-secondary">{helper}</div>
              </div>
            </div>
            <button type="button" aria-label="关闭数学符号面板" onClick={closePanel} className="math-input-close flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-text-secondary hover:bg-[var(--surface-muted)] hover:text-text-primary">
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          {view === 'templates' && (
            <>
              <div className="flex items-center gap-1 overflow-x-auto border-b border-border px-2 py-1.5" role="tablist" aria-label="数学符号分类">
                {mathTemplateCategories.map((option) => (
                  <button key={option.id} type="button" role="tab" aria-selected={category === option.id} onClick={() => setCategory(option.id)} className={`flex-shrink-0 rounded-lg px-3 py-1.5 type-caption font-medium ${category === option.id ? 'bg-[var(--accent-soft)] text-accent' : 'text-text-secondary hover:bg-[var(--surface-muted)] hover:text-text-primary'}`}>
                    {option.label}
                  </button>
                ))}
                <button type="button" onClick={() => { setMatrixSize([2, 2]); setView('matrix'); }} className="ml-auto flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 type-caption font-medium text-text-secondary hover:border-accent/40 hover:text-accent">
                  <Grid3X3 className="h-3.5 w-3.5" />矩阵输入
                </button>
              </div>

              <div className="max-h-[min(48vh,340px)] overflow-y-auto p-2.5">
                <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-6">
                  {templates.map((template) => (
                    <button key={template.id} type="button" onClick={() => beginFormula(template)} className="math-input-template min-h-14 rounded-lg border border-border bg-bg-card px-2 py-1.5 text-center hover:border-accent/40 hover:bg-[var(--accent-softer)]" title={template.description}>
                      <span className="block font-[var(--font-math)] text-[15px] leading-5 text-text-primary">{template.label}</span>
                      <span className="mt-0.5 block truncate type-micro text-text-secondary">{template.description}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {view === 'editor' && (
            <div className="p-3">
              <MathFieldEditor ref={mathFieldRef} key={editorKey} value={editorLatex} onChange={setEditorLatex} autoFocus />
              <div className="math-quick-key-row mt-2 flex gap-1 overflow-x-auto pb-1" role="toolbar" aria-label="公式快捷键">
                {mathQuickKeys.map((key) => (
                  <button
                    key={key.id}
                    type="button"
                    title={key.description}
                    aria-label={key.description}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => mathFieldRef.current?.insert(key.latex)}
                    className="math-quick-key flex h-8 min-w-8 flex-shrink-0 items-center justify-center rounded-md border border-border bg-bg-card px-2 font-[var(--font-math)] text-sm text-text-primary hover:border-accent/40 hover:bg-[var(--accent-softer)] hover:text-accent"
                  >
                    {key.label}
                  </button>
                ))}
              </div>
              <div className="mt-2 flex rounded-lg border border-border bg-[var(--surface-subtle)] p-1">
                <button type="button" onClick={() => setDisplayMode(false)} className={`flex-1 rounded-md px-3 py-1.5 type-caption font-medium ${!displayMode ? 'bg-bg-card text-accent' : 'text-text-secondary'}`}>行内公式</button>
                <button type="button" onClick={() => setDisplayMode(true)} className={`flex-1 rounded-md px-3 py-1.5 type-caption font-medium ${displayMode ? 'bg-bg-card text-accent' : 'text-text-secondary'}`}>独立公式</button>
              </div>
              {hasUnfilledPlaceholder(editorLatex) && <div className="mt-2 type-caption text-[var(--warning-text)]">请填写公式中的所有灰色占位框。</div>}
              <div className="mt-3 flex justify-end gap-2">
                <button type="button" onClick={() => { setView('templates'); setEditingId(null); }} className="rounded-lg border border-border px-3 py-2 type-control text-text-secondary hover:bg-[var(--surface-muted)]">返回</button>
                <button type="button" disabled={editorInvalid} onClick={saveFormula} className="rounded-lg bg-accent px-4 py-2 type-control text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40">{editingId ? '保存修改' : '插入问答框'}</button>
              </div>
            </div>
          )}

          {view === 'matrix' && <MatrixBuilder key={`${matrixSize[0]}-${matrixSize[1]}`} initialRows={matrixSize[0]} initialColumns={matrixSize[1]} onCancel={() => setView('templates')} onSave={saveMatrix} />}
        </div>
      )}
    </div>
  );
};

export default VisualMathInputPopover;
