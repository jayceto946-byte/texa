import { TexaTextbook } from '../icons';
import React from 'react';
import { Printer } from 'lucide-react';
import type { ChatChapterHighlightCard } from '../../types';
import { SimpleMarkdown } from './MarkdownMessage';

const ChapterHighlightCard: React.FC<{ card: ChatChapterHighlightCard }> = ({ card }) => {
  const isSection = card.scope_type === 'section' || Boolean(card.section_id);
  const label = isSection ? '小节重点' : '章节重点';
  const scopeTitle = card.scope_title || card.section_title || card.chapter_title;
  return (
    <div className="chapter-highlight-print space-y-3">
      <div className="rounded-xl border border-border bg-[var(--surface-subtle)] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold text-text-primary"><TexaTextbook className="h-4 w-4 text-accent" />{label}</div>
            <div className="mt-1 text-xs text-text-secondary">{card.book_name} · {scopeTitle}{card.generated_at ? ` · ${card.generated_at}` : ''}</div>
          </div>
          <button type="button" onClick={() => window.print()} className="no-print inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs text-text-primary hover:border-accent/50 hover:text-accent">
            <Printer className="h-3.5 w-3.5" /> 打印
          </button>
        </div>
      </div>
      <div className="rounded-xl border border-border bg-bg-card p-4">
        <SimpleMarkdown content={card.markdown} />
      </div>
    </div>
  );
};

export default ChapterHighlightCard;