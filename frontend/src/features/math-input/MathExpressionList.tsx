import React from 'react';
import { Pencil, Trash2 } from 'lucide-react';

import { SimpleMarkdown } from '../../components/chat/MarkdownRenderer';
import type { MathExpression } from './types';

interface MathExpressionListProps {
  expressions: MathExpression[];
  onEdit: (expression: MathExpression) => void;
  onRemove: (id: string) => void;
  onReference: (referenceNumber: number) => void;
}

const MathExpressionList: React.FC<MathExpressionListProps> = ({ expressions, onEdit, onRemove, onReference }) => {
  if (!expressions.length) return null;

  return (
    <div className="math-attachment-list bg-[var(--surface-subtle)] px-3 py-2.5" aria-label="问答框中的公式">
      <div className="flex flex-wrap gap-1.5">
        {expressions.map((expression, index) => {
          const referenceNumber = expression.referenceNumber ?? index + 1;
          return (
            <div key={expression.id} className="group flex min-h-9 max-w-full items-center gap-1.5 rounded-lg border border-accent/20 bg-bg-card py-1 pl-2.5 pr-1">
              <button
                type="button"
                onClick={() => onReference(referenceNumber)}
                title={`在问题中引用公式${referenceNumber}`}
                className="flex-shrink-0 rounded bg-[var(--accent-soft)] px-1.5 py-0.5 type-micro font-medium text-accent hover:bg-accent hover:text-white"
              >
                公式{referenceNumber}
              </button>
              <div className="max-w-[min(48vw,300px)] overflow-x-auto px-1 text-sm">
                <SimpleMarkdown content={expression.displayMode ? `$$\n${expression.latex}\n$$` : `$${expression.latex}$`} />
              </div>
              <div className="flex flex-shrink-0 items-center gap-0.5 border-l border-border/70 pl-1">
                <button type="button" aria-label={`编辑公式${referenceNumber}`} title="编辑公式" onClick={() => onEdit(expression)} className="flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:bg-[var(--surface-muted)] hover:text-accent"><Pencil className="h-3.5 w-3.5" /></button>
                <button type="button" aria-label={`删除公式${referenceNumber}`} title="从问答框移除" onClick={() => onRemove(expression.id)} className="flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:bg-red-50 hover:text-red-700"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-1.5 type-micro text-text-secondary">点击“公式1”等编号，可插入到问题中引用</p>
    </div>
  );
};

export default MathExpressionList;
