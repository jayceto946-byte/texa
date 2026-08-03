import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookMarked, BookOpenCheck, BrainCircuit, CalendarDays, ClipboardList, Loader2, MessageSquareText, Shuffle } from 'lucide-react';
import { get } from '../../api/client';
import { scopeContainsBook, type TextbookScopeOption } from '../../utils/textbookScopes';

export type ChatHomeBookOption = TextbookScopeOption;

export type ChatHomeDueMistake = {
  id: string;
  question_text?: string;
  subject?: string;
  chapter?: string | null;
  tags?: string[];
  linked_concepts?: Array<{ name: string }>;
  mistake_type?: string[];
};

export type ChatHomeConceptPlan = {
  name: string;
  reasons?: string[];
  related_mistakes?: ChatHomeDueMistake[];
  exposure_count?: number;
  priority?: number;
};

export type ChatHomeLearningSummary = {
  due_mistakes?: ChatHomeDueMistake[];
  concept_review_plan?: ChatHomeConceptPlan[];
  mistake_stats?: { due_today?: number; total?: number; by_type?: Record<string, number>; by_tag?: Record<string, number> };
  mistake_weak_points?: Array<{ name: string; count?: number; type?: string }>;
  weak_concepts?: Array<{ name: string; reasons?: string[] }>;
};

type ChatHomePanelProps = {
  bookName: string;
  subject: string;
  books: ChatHomeBookOption[];
  isLoading: boolean;
  onReviewMistake: (mistake: ChatHomeDueMistake) => void;
  onReviewConcept: (concept: ChatHomeConceptPlan, summary: ChatHomeLearningSummary | null) => void;
  onPracticeFromMemory: (summary: ChatHomeLearningSummary | null) => void;
  onShowReport: (mode: 'daily' | 'weekly') => void;
  onPickRandomExercise: () => void;
  onOpenHighlightDialog: () => void;
  onOpenMistakeQuickCapture: () => void;
};

function firstLine(value = '') {
  const line = value.replace(/\s+/g, ' ').trim();
  return line.length > 54 ? `${line.slice(0, 54)}...` : line;
}

export default function ChatHomePanel({
  bookName, subject, books, isLoading, onReviewMistake, onReviewConcept,
  onPracticeFromMemory, onShowReport, onPickRandomExercise, onOpenHighlightDialog,
  onOpenMistakeQuickCapture,
}: ChatHomePanelProps) {
  const [summary, setSummary] = useState<ChatHomeLearningSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!bookName) {
      setSummary(null);
      setFailed(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setFailed(false);
    const params = new URLSearchParams({ book_name: bookName, subject, limit: '12' });
    get(`/kg/learning-summary?${params.toString()}`, 30000)
      .then((res) => {
        if (!alive) return;
        setSummary(res?.success ? res.data || null : null);
        setFailed(!res?.success);
      })
      .catch(() => {
        if (!alive) return;
        setSummary(null);
        setFailed(true);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => { alive = false; };
  }, [bookName, subject]);

  const dueMistakes = summary?.due_mistakes || [];
  const firstMistake = dueMistakes[0];
  const firstConcept = summary?.concept_review_plan?.[0];
  const currentScope = books.find((book) => scopeContainsBook(book, bookName));
  const scopeLabel = `${subject || '未限定学科'} / ${currentScope?.displayName || currentScope?.name || bookName || '通用问答'}`;
  const recommended = firstMistake
    ? {
        icon: <BookOpenCheck className="h-4 w-4" />,
        title: `${dueMistakes.length} 道错题已到复习时间`,
        description: firstLine(firstMistake.question_text),
        action: () => onReviewMistake(firstMistake),
        link: <Link to={`/mistakes?mistake_id=${encodeURIComponent(firstMistake.id)}`} className="type-caption text-accent hover:underline">查看错题本</Link>,
      }
    : firstConcept
      ? {
          icon: <BrainCircuit className="h-4 w-4" />,
          title: `建议复习：${firstConcept.name}`,
          description: firstConcept.reasons?.[0] || '根据近期学习记录生成',
          action: () => onReviewConcept(firstConcept, summary),
          link: <Link to="/learning" className="type-caption text-accent hover:underline">查看学习情况</Link>,
        }
      : null;

  return (
    <div className="mx-auto flex min-h-[52vh] w-full max-w-3xl flex-col justify-center py-7">
      <header className="mb-7">
        <div className="flex items-center gap-2">
          <MessageSquareText className="h-5 w-5 text-accent" />
          <h2 className="type-title text-text-primary">开始一段学习对话</h2>
          {loading && <Loader2 className="h-4 w-4 animate-spin text-accent" />}
        </div>
        <p className="type-body mt-2 text-text-secondary">可以提问、复习概念，或从一道题开始。</p>
        <p className="type-caption mt-1 text-text-secondary">{scopeLabel}</p>
      </header>

      {recommended && (
        <section className="mb-6 border-y border-border py-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-accent">{recommended.icon}</span>
            <div className="min-w-0 flex-1">
              <h3 className="type-section-title text-text-primary">{recommended.title}</h3>
              <p className="type-body mt-1 text-text-secondary">{recommended.description}</p>
              <div className="mt-1.5">{recommended.link}</div>
            </div>
            <button type="button" onClick={recommended.action} disabled={isLoading} className="app-primary-button flex-shrink-0 disabled:opacity-45">开始复习</button>
          </div>
        </section>
      )}

      <section aria-label="开始方式">
        <h3 className="type-caption mb-2 font-medium text-text-secondary">你也可以</h3>
        <div className="grid border-y border-border sm:grid-cols-2">
          <QuickAction icon={<BrainCircuit className="h-4 w-4" />} label="按薄弱点练习" onClick={() => onPracticeFromMemory(summary)} disabled={isLoading} />
          <QuickAction icon={<Shuffle className="h-4 w-4" />} label="随机抽一道题" onClick={onPickRandomExercise} disabled={isLoading} />
          <QuickAction icon={<BookMarked className="h-4 w-4" />} label="查看教材重点" onClick={onOpenHighlightDialog} disabled={!books.length || isLoading} />
          <QuickAction icon={<CalendarDays className="h-4 w-4" />} label="查看今日报告" onClick={() => onShowReport('daily')} disabled={isLoading} />
        </div>
        <button type="button" onClick={onOpenMistakeQuickCapture} disabled={isLoading} className="type-caption mt-3 inline-flex items-center gap-1.5 text-text-secondary hover:text-accent disabled:opacity-45"><ClipboardList className="h-3.5 w-3.5" />快速录入错题</button>
      </section>
      {failed && <p className="type-caption mt-3 text-[var(--warning-text)]">学习摘要暂时不可用，仍可直接提问或使用快捷操作。</p>}
    </div>
  );
}

function QuickAction({ icon, label, disabled, onClick }: { icon: React.ReactNode; label: string; disabled?: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="type-control flex w-full items-center gap-3 border-b border-border px-3 py-3 text-left text-text-primary hover:bg-[var(--accent-softer)] disabled:cursor-not-allowed disabled:opacity-45 sm:odd:border-r">
      <span className="text-accent">{icon}</span>
      <span>{label}</span>
    </button>
  );
}
