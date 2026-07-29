import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookMarked, CalendarDays, ImagePlus, Send, Shuffle, Square } from 'lucide-react';
import { get, post } from '../api/client';

import HighlightRepositoryDialog from '../components/HighlightRepositoryDialog';
import ChatHomePanel, { type ChatHomeConceptPlan, type ChatHomeDueMistake, type ChatHomeLearningSummary } from '../components/chat/ChatHomePanel';
import ChatMessage from '../components/ChatMessage';
import ScopeSelector from '../components/ScopeSelector';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useChatContext, type ChatMessage as ContextChatMessage } from '../contexts/ChatContext';
import { composeMathQuestion } from '../features/math-input/composeMathQuestion';
import { insertFormulaReference } from '../features/math-input/formulaReferences';
import MathExpressionList from '../features/math-input/MathExpressionList';
import type { MathEditRequest, MathExpression } from '../features/math-input/types';
import VisualMathInputPopover from '../features/math-input/VisualMathInputPopover';
import { useChat } from '../hooks/useChat';
import type { ExerciseRecord } from '../types';
import { buildTextbookScopeOptions, findDefaultTextbookScope, scopeContainsBook, type TextbookRecord } from '../utils/textbookScopes';
type ReportMode = 'daily' | 'weekly';
type ActionMode = ReportMode | 'exercise';

function firstLine(value = '', maxLength = 48) {
  const line = value.replace(/\s+/g, ' ').trim();
  return line.length > maxLength ? `${line.slice(0, maxLength)}...` : line;
}

function uniqueTexts(values: string[]) {
  const seen = new Set<string>();
  const next: string[] = [];
  for (const value of values) {
    const text = value.trim();
    const key = text.toLowerCase();
    if (!text || seen.has(key)) continue;
    seen.add(key);
    next.push(text);
  }
  return next;
}

function focusTermsFromSummary(summary: ChatHomeLearningSummary | null) {
  const values: string[] = [];
  for (const item of summary?.concept_review_plan || []) values.push(item.name);
  for (const item of summary?.mistake_weak_points || []) values.push(item.name);
  for (const item of summary?.weak_concepts || []) values.push(item.name);
  for (const mistake of summary?.due_mistakes || []) {
    values.push(mistake.chapter || '');
    values.push(...(mistake.tags || []));
    values.push(...(mistake.linked_concepts || []).map((item) => item.name));
  }
  return uniqueTexts(values).slice(0, 16);
}

function recordMatchesTerms(record: ExerciseRecord, terms: string[]) {
  if (!terms.length) return false;
  const haystack = [
    record.question_text,
    record.answer,
    record.explanation,
    record.subject,
    record.chapter || '',
    record.source,
    ...(record.tags || []),
    ...(record.linked_concepts || []).map((item) => item.name),
  ].join('\n').toLowerCase();
  return terms.some((term) => haystack.includes(term.toLowerCase()));
}


const ChatPage: React.FC = () => {
  const [input, setInput] = useState('');
  const [mathExpressions, setMathExpressions] = useState<MathExpression[]>([]);
  const [mathEditRequest, setMathEditRequest] = useState<MathEditRequest | null>(null);
  const [books, setBooks] = useState<TextbookRecord[]>([]);
  const [booksLoaded, setBooksLoaded] = useState(false);
  const [highlightDialogOpen, setHighlightDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<ActionMode | null>(null);
  const { messages, isLoading, sendMessage, stop } = useChat();
  const { bookName, setBookName, subject, setSubject, conversationId, addMessage } = useChatContext();
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mathExpressionSequenceRef = useRef(0);
  const mathEditSequenceRef = useRef(0);
  const subjectSuggestions = Array.from(new Set(books.map((book) => book.subject || '').filter(Boolean)));
  const scopeBooks = useMemo(() => buildTextbookScopeOptions(books), [books]);

  useEffect(() => {
    const loadBooks = async () => {
      try {
        const res = await get('/books/list');
        if (res?.success) setBooks(res.data || []);
      } catch {
        setBooks([]);
      } finally {
        setBooksLoaded(true);
      }
    };
    const onChanged = () => loadBooks();
    window.addEventListener('books:changed', onChanged);
    loadBooks();
    return () => window.removeEventListener('books:changed', onChanged);
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const persistLocalExchange = async (userContent: string, assistantContent: string) => {
    try {
      await post('/chat/log', {
        conversation_id: conversationId,
        book_name: bookName,
        subject,
        messages: [
          { role: 'user', content: userContent },
          { role: 'assistant', content: assistantContent },
        ],
      }, 15000);
    } catch {
      // Local workflow cards should stay usable even if the backend has not been restarted yet.
    }
  };

  const addLocalExchange = (userContent: string, assistantContent: string, extra: Partial<ContextChatMessage> = {}) => {
    addMessage({ role: 'user', content: userContent });
    addMessage({ role: 'assistant', content: assistantContent, stage: 'done', ...extra });
    void persistLocalExchange(userContent, assistantContent);
  };

  const switchBook = useCallback(async (name: string) => {
    if (!name) {
      setBookName('');
      return;
    }
    try {
      const res = await get(`/books/switch/${encodeURIComponent(name)}`);
      if (res?.success) {
        setBookName(res.data.name);
        if (res.data.subject) setSubject(res.data.subject);
      }
    } catch {
      setBookName(name);
    }
  }, [setBookName, setSubject]);

  useEffect(() => {
    if (!booksLoaded) return;
    if (bookName) {
      if (!scopeBooks.some((scope) => scopeContainsBook(scope, bookName))) setBookName('');
      return;
    }
    const target = findDefaultTextbookScope(scopeBooks, subject);
    if (target) void switchBook(target.name);
  }, [bookName, booksLoaded, scopeBooks, setBookName, subject, switchBook]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const question = composeMathQuestion(input, mathExpressions);
    if (!question || isLoading) return;
    sendMessage(question);
    setInput('');
    setMathExpressions([]);
    setMathEditRequest(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleAddMathExpression = (latex: string, displayMode: boolean) => {
    const id = `math-${Date.now()}-${++mathExpressionSequenceRef.current}`;
    setMathExpressions((current) => {
      const referenceNumber = current.reduce(
        (maximum, item, index) => Math.max(maximum, item.referenceNumber ?? index + 1),
        0,
      ) + 1;
      return [...current, { id, latex, displayMode, referenceNumber }];
    });
  };

  const handleUpdateMathExpression = (id: string, latex: string, displayMode: boolean) => {
    setMathExpressions((current) => current.map((item) => (
      item.id === id ? { ...item, latex, displayMode } : item
    )));
    setMathEditRequest(null);
  };

  const handleEditMathExpression = (expression: MathExpression) => {
    setMathEditRequest({
      nonce: ++mathEditSequenceRef.current,
      expression,
    });
  };

  const handleRemoveMathExpression = (id: string) => {
    setMathExpressions((current) => current.filter((item) => item.id !== id));
    setMathEditRequest((current) => current?.expression.id === id ? null : current);
  };

  const handleReferenceMathExpression = (referenceNumber: number) => {
    const field = textareaRef.current;
    const insertion = insertFormulaReference(
      input,
      referenceNumber,
      field?.selectionStart ?? input.length,
      field?.selectionEnd ?? input.length,
    );
    setInput(insertion.text);
    window.requestAnimationFrame(() => {
      field?.focus({ preventScroll: true });
      field?.setSelectionRange(insertion.cursor, insertion.cursor);
      if (field) field.style.height = Math.min(field.scrollHeight, 160) + 'px';
    });
  };

  const showReport = async (mode: ReportMode) => {
    if (actionLoading) return;
    const isDaily = mode === 'daily';
    const title = isDaily ? '学习日报' : '学习周报';
    const userContent = `展示我的${title}`;
    addMessage({ role: 'user', content: userContent });
    setActionLoading(mode);
    try {
      const params = new URLSearchParams({ book_name: bookName || 'default', subject, days: isDaily ? '1' : '7' });
      const res = await get(`/reports/weekly?${params.toString()}`);
      if (!res?.success) throw new Error(res?.message || `生成${title}失败`);
      addMessage({ role: 'assistant', content: '', stage: 'done', reportCard: { kind: mode, report: res.data } });
      void persistLocalExchange(userContent, `${title}已整理，可在当前对话中查看卡片。`);
    } catch (err) {
      addMessage({ role: 'assistant', content: `出错了：${err instanceof Error ? err.message : String(err)}`, stage: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  const pickRandomExercise = async () => {
    if (actionLoading) return;
    const userContent = '随机抽一道习题';
    addMessage({ role: 'user', content: userContent });
    setActionLoading('exercise');
    const bookQuery = bookName ? `?book_name=${encodeURIComponent(bookName)}` : '';
    try {
      const statuses = ['needs_review', 'practicing', 'new', ''];
      let pool: ExerciseRecord[] = [];
      for (const status of statuses) {
        const res = await post(`/exercises/list${bookQuery}`, { search_kw: '', subject, status, limit: 100 });
        if (res?.success && Array.isArray(res.data) && res.data.length) {
          const rows = res.data as ExerciseRecord[];
          pool = status ? rows : rows.filter((item) => item.status !== 'mastered');
          if (pool.length) break;
        }
      }
      if (!pool.length) {
        const content = '习题库里暂时没有可抽取的题目。可以先在“习题库”导入 Word/PDF，或从错题本转入习题。';
        addMessage({ role: 'assistant', content, stage: 'done' });
        void persistLocalExchange(userContent, content);
        return;
      }
      const record = pool[Math.floor(Math.random() * pool.length)];
      addMessage({ role: 'assistant', content: '', stage: 'done', exerciseCard: { record } });
      void persistLocalExchange(userContent, `已从题库抽取：${firstLine(record.question_text, 72)}`);
    } catch (err) {
      addMessage({ role: 'assistant', content: `出错了：${err instanceof Error ? err.message : String(err)}`, stage: 'error' });
    } finally {
      setActionLoading(null);
    }
  };


  const reviewMistakeFromSummary = (mistake: ChatHomeDueMistake) => {
    if (actionLoading) return;
    const concepts = (mistake.linked_concepts || []).map((item) => item.name).filter(Boolean);
    const tags = mistake.tags || [];
    const assistantContent = [
      '## 到期错题复习',
      '',
      `**题目**：${mistake.question_text || '未命名错题'}`,
      mistake.chapter ? `**章节**：${mistake.chapter}` : '',
      concepts.length ? `**涉及概念**：${concepts.join('、')}` : '',
      tags.length ? `**标签**：${tags.join('、')}` : '',
      '',
      '建议先独立重做一遍，再回到错题本核对答案、错因和复习评级。',
    ].filter(Boolean).join('\n');
    addLocalExchange(`复习错题：${firstLine(mistake.question_text || mistake.id)}`, assistantContent, {
      linkedConcepts: concepts.map((name) => ({ name })),
    });
  };

  const reviewConceptFromSummary = (concept: ChatHomeConceptPlan, summary: ChatHomeLearningSummary | null) => {
    if (actionLoading) return;
    const relatedMistakes = concept.related_mistakes || (summary?.due_mistakes || []).filter((mistake) => {
      const names = (mistake.linked_concepts || []).map((item) => item.name);
      return names.includes(concept.name) || (mistake.tags || []).includes(concept.name);
    });
    const assistantContent = [
      `## 概念复习：${concept.name}`,
      '',
      concept.reasons?.length ? `复习原因：${concept.reasons.slice(0, 2).join('；')}` : '复习原因：该概念出现在近期薄弱记录中。',
      relatedMistakes.length ? '' : '',
      relatedMistakes.length ? '### 相关错题线索' : '',
      ...relatedMistakes.slice(0, 3).map((item, index) => `${index + 1}. ${firstLine(item.question_text || item.id, 72)}`),
      '',
      '下一步：先用自己的话说出定义、适用条件和常见误区，再抽一道相关题检查。',
    ].filter(Boolean).join('\n');
    addLocalExchange(`复习概念：${concept.name}`, assistantContent, { linkedConcepts: [{ name: concept.name }] });
  };

  const practiceFromMemory = async (summary: ChatHomeLearningSummary | null) => {
    if (actionLoading) return;
    const userContent = '按薄弱点抽一道题';
    const terms = focusTermsFromSummary(summary);
    addMessage({ role: 'user', content: userContent });
    setActionLoading('exercise');
    const bookQuery = bookName ? `?book_name=${encodeURIComponent(bookName)}` : '';
    try {
      const statuses = ['needs_review', 'practicing', 'new', ''];
      let pool: ExerciseRecord[] = [];
      let fallback: ExerciseRecord[] = [];
      for (const status of statuses) {
        const res = await post(`/exercises/list${bookQuery}`, { search_kw: '', subject, status, limit: 120 });
        if (!res?.success || !Array.isArray(res.data)) continue;
        const rows = (res.data as ExerciseRecord[]).filter((item) => item.status !== 'mastered');
        fallback = [...fallback, ...rows];
        const matched = terms.length ? rows.filter((record) => recordMatchesTerms(record, terms)) : rows;
        if (matched.length) {
          pool = matched;
          break;
        }
      }
      if (!pool.length) pool = fallback;
      if (!pool.length) {
        const content = terms.length
          ? `已经定位到薄弱线索：${terms.slice(0, 5).join('、')}，但习题库里暂时没有匹配题。可以先导入 Word/PDF 题库，或从错题本转入习题。`
          : '学习记录里还没有可用薄弱点，习题库也没有可抽取题目。可以先导入题库或录入错题。';
        addMessage({ role: 'assistant', content, stage: 'done' });
        void persistLocalExchange(userContent, content);
        return;
      }
      const record = pool[Math.floor(Math.random() * pool.length)];
      addMessage({ role: 'assistant', content: '', stage: 'done', exerciseCard: { record } });
      const matchedTerms = terms.filter((term) => recordMatchesTerms(record, [term])).slice(0, 5);
      const assistantText = matchedTerms.length
        ? `已按薄弱点 ${matchedTerms.join('、')} 抽题：${firstLine(record.question_text, 72)}`
        : `已从待复习题库抽题：${firstLine(record.question_text, 72)}`;
      void persistLocalExchange(userContent, assistantText);
    } catch (err) {
      addMessage({ role: 'assistant', content: `出错了：${err instanceof Error ? err.message : String(err)}`, stage: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  const openMistakeQuickCapture = () => {
    const userContent = '打开错题速录';
    const assistantContent = '已打开错题速录卡片，可以上传图片、粘贴题干并校正识别结果。';
    addMessage({ role: 'user', content: userContent });
    addMessage({ role: 'assistant', content: '', stage: 'done', utilityCard: { kind: 'mistake_quick_capture' } });
    void persistLocalExchange(userContent, assistantContent);
  };

  const openHighlightDialog = () => {
    if (actionLoading) return;
    setHighlightDialogOpen(true);
  };

  return (
    <div className="relative flex h-full min-w-0 bg-bg-primary">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="app-page-header desktop-chat-header hidden border-b border-border bg-bg-secondary/86 backdrop-blur sm:flex">
          <h2 className="app-page-title">学习对话</h2>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 sm:px-5 sm:py-6">
          <div className="mx-auto max-w-5xl space-y-2">
            {messages.length === 0 && (
              <ChatHomePanel
                bookName={bookName}
                subject={subject}
                books={scopeBooks}
                isLoading={isLoading || Boolean(actionLoading)}
                onReviewMistake={reviewMistakeFromSummary}
                onReviewConcept={reviewConceptFromSummary}
                onPracticeFromMemory={practiceFromMemory}
                onShowReport={showReport}
                onPickRandomExercise={pickRandomExercise}
                onOpenHighlightDialog={openHighlightDialog}
                onOpenMistakeQuickCapture={openMistakeQuickCapture}
              />
            )}
            {messages.map((msg, i) => (
              <ErrorBoundary key={msg.id || `${msg.turnId || 'message'}-${i}`}>
                <ChatMessage role={msg.role} content={msg.content} stage={msg.stage} turnId={msg.turnId} subjectSuggestion={msg.subjectSuggestion} linkedConcepts={msg.linkedConcepts} reportCard={msg.reportCard} exerciseCard={msg.exerciseCard} chapterHighlightCard={msg.chapterHighlightCard} utilityCard={msg.utilityCard} agentCard={msg.agentCard} />
              </ErrorBoundary>
            ))}
          </div>
        </div>

        <div className="chat-composer border-t border-border bg-bg-secondary/86 p-2 backdrop-blur sm:p-4">
          <form onSubmit={handleSubmit} className="mx-auto flex max-w-5xl items-end gap-2">
            <VisualMathInputPopover
              disabled={isLoading}
              editRequest={mathEditRequest}
              onAddExpression={handleAddMathExpression}
              onUpdateExpression={handleUpdateMathExpression}
            />
            <div className="chat-question-box min-w-0 flex-1 overflow-hidden rounded-xl border border-border bg-bg-card transition-colors focus-within:border-accent">
              <MathExpressionList
                expressions={mathExpressions}
                onEdit={handleEditMathExpression}
                onRemove={handleRemoveMathExpression}
                onReference={handleReferenceMathExpression}
              />
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                placeholder={mathExpressions.length ? '继续描述问题，点击公式编号可引用…' : '输入问题...'}
                disabled={isLoading}
                className="max-h-[108px] min-h-[40px] w-full resize-none overflow-y-auto border-0 bg-transparent px-4 py-2 type-body text-text-primary outline-none shadow-none placeholder-text-secondary focus:shadow-none sm:max-h-[160px] sm:min-h-[48px] sm:px-5 sm:py-3"
              />
            </div>
            {isLoading ? (
              <button type="button" onClick={stop} className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg border border-red-300 bg-red-50 text-red-700 transition-colors hover:bg-red-100">
                <Square className="h-4 w-4 fill-current" />
              </button>
            ) : (
              <button type="submit" disabled={!input.trim() && mathExpressions.length === 0} className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40">
                <Send className="h-4 w-4" />
              </button>
            )}
          </form>

          {messages.length > 0 && <div className="chat-toolbar mx-auto mt-2 max-w-5xl">
            <div className="chat-scope-control mb-1.5 sm:mb-0 sm:inline-flex">
              <ScopeSelector
                subject={subject}
                bookName={bookName}
                books={scopeBooks}
                suggestions={subjectSuggestions}
                onSubjectChange={setSubject}
                onBookChange={switchBook}
                placement="top"
                width="wide"
                disabled={isLoading}
              />
            </div>
            <div className="mobile-action-row flex flex-wrap items-center gap-1.5 overflow-visible pb-0 sm:inline-flex sm:gap-2 sm:pl-2">
              <button type="button" onClick={() => showReport('daily')} disabled={Boolean(actionLoading)} className={`flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg border px-3 type-control transition-colors ${actionLoading === 'daily' ? 'border-accent/30 bg-[var(--accent-soft)] text-accent' : 'border-border bg-bg-card text-text-secondary hover:border-accent/40 hover:text-text-primary'} disabled:opacity-60`}>
                <CalendarDays className="h-3.5 w-3.5" />
                {actionLoading === 'daily' ? '整理日报' : '学习日报'}
              </button>
              <button type="button" onClick={() => showReport('weekly')} disabled={Boolean(actionLoading)} className={`flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg border px-3 type-control transition-colors ${actionLoading === 'weekly' ? 'border-accent/30 bg-[var(--accent-soft)] text-accent' : 'border-border bg-bg-card text-text-secondary hover:border-accent/40 hover:text-text-primary'} disabled:opacity-60`}>
                <CalendarDays className="h-3.5 w-3.5" />
                {actionLoading === 'weekly' ? '整理周报' : '学习周报'}
              </button>
              <button type="button" onClick={pickRandomExercise} disabled={Boolean(actionLoading)} className={`flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg border px-3 type-control transition-colors ${actionLoading === 'exercise' ? 'border-accent/30 bg-[var(--accent-soft)] text-accent' : 'border-border bg-bg-card text-text-secondary hover:border-accent/40 hover:text-text-primary'} disabled:opacity-60`}>
                <Shuffle className="h-3.5 w-3.5" />
                {actionLoading === 'exercise' ? '抽题中' : '随机抽题'}
              </button>
              <button type="button" onClick={openHighlightDialog} disabled={Boolean(actionLoading)} className="flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg border border-border bg-bg-card px-3 type-control text-text-secondary transition-colors hover:border-accent/40 hover:text-text-primary disabled:opacity-60">
                <BookMarked className="h-3.5 w-3.5" />
                查看/生成重点
              </button>
              <button type="button" onClick={openMistakeQuickCapture} className="flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg border border-border bg-bg-card px-3 type-control text-text-secondary transition-colors hover:border-accent/40 hover:text-text-primary">
                <ImagePlus className="h-3.5 w-3.5" />
                错题速录
              </button>
            </div>
          </div>}
        </div>
      </div>
      <HighlightRepositoryDialog
        open={highlightDialogOpen}
        books={books}
        currentBookName={bookName}

        onClose={() => setHighlightDialogOpen(false)}
      />
    </div>
  );
};

export default ChatPage;
