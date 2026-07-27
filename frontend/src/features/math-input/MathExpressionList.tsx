import React from 'react';
import { Pencil, Trash2 } from 'lucide-react';

import { SimpleMarkdown } from '../../components/chat/MarkdownRenderer';
import type { MathExpression } from './types';

interface MathExpressionListProps {
  expressions: MathExpression[];
  onEdit: (expression: MathExpression) => void;
  onRemove: (id: string) => void;
}

const MathExpressionList: React.FC<MathExpressionListProps> = ({ expressions, onEdit, onRemove }) => {
  if (!expressions.length) return null;

  return (
    <div className="math-attachment-list flex flex-wrap gap-1.5 px-3 pt-2.5" aria-label="问答框中的公式">
      {expressions.map((expression, index) => (
        <div key={expression.id} className="group flex min-h-9 max-w-full items-center gap-1.5 rounded-lg border border-accent/20 bg-[var(--accent-softer)] py-1 pl-2.5 pr-1">
          <span className="flex-shrink-0 rounded bg-[var(--accent-soft)] px-1.5 py-0.5 type-micro font-medium text-accent">
            公式 {index + 1}
          </span>
          <div className="max-w-[min(48vw,300px)] overflow-x-auto px-1 text-sm">
            <SimpleMarkdown content={expression.displayMode ? `$$\n${expression.latex}\n$$` : `$${expression.latex}$`} />
          </div>
          <div className="flex flex-shrink-0 items-center gap-0.5 border-l border-border/70 pl-1">
            <button type="button" aria-label={`编辑公式 ${index + 1}`} title="编辑公式" onClick={() => onEdit(expression)} className="flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:bg-bg-card hover:text-accent"><Pencil className="h-3.5 w-3.5" /></button>
            <button type="button" aria-label={`删除公式 ${index + 1}`} title="从问答框移除" onClick={() => onRemove(expression.id)} className="flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:bg-red-50 hover:text-red-700"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default MathExpressionList;
