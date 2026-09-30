import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen,
  BrainCircuit,
  CalendarDays,
  ChevronDown,
  ClipboardList,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import { get, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import ScopeSelector, { type ScopeBookOption } from '../components/ScopeSelector';
import { ActionableIssue, PageState, TaskStatus } from '../components/ui/AsyncState';
import { useChatContext } from '../contexts/ChatContext';
import type { ConceptCandidate, ReviewHistoryItem } from '../types';
import './LearningPage.css';

interface LearningMistakeSummary {
  id: string;
  question_text: string;
  source?: string;
  subject?: string;
  chapter?: string | null;
  tags?: string[];
  mistake_type?: string[];
  next_review?: string | null;
  interval?: number | null;
  review_history?: ReviewHistoryItem[];
  linked_concepts?: ConceptCandidate[];
}

interface ConceptReviewCardData {
  name: string;
  priority: number;
  reasons: string[];
  days_since_seen?: number | null;
  days_since_review?: number | null;
  exposure_count: number;
  mastery_level?: number;
  weak?: boolean;
  recent_questions: Array<{ question: string; source: string; timestamp: string; weak?: boolean; mistake_id?: string }>;
  related_mistakes: LearningMistakeSummary[];
  textbook_snippets: Array<{ type: string; text: string; chapter?: string }>;
}

interface DailySubjectDetail {
  subject: string;
  book_name?: string;
  qa: number;
  mistake: number;
  total: number;
  concepts: Array<{ name: string; count: number }>;
}

interface DailyDetail {
  date: string;
  qa: number;
  mistake: number;
  total: number;
  subjects: DailySubjectDetail[];
}

interface LearningSummary {
  stats: {
    total_concepts: number;
    total_exposures: number;
    weak_count: number;
    forgotten_count: number;
  };
  top_concepts: Array<{ name: string; count: number; weak_flag?: boolean; source_chapters?: string[] }>;
  weak_concepts: Array<{ name: string; exposure_count: number; weak_reason?: string; last_weak_at?: string }>;
  review_queue: Array<{ name: string; reason: string }>;
  concept_review_plan: ConceptReviewCardData[];
  daily: Array<{ date: string; qa: number; mistake: number; total: number }>;
  daily_details?: DailyDetail[];
  mistake_stats: { total: number; due_today: number };
  mistake_weak_points: Array<{ name: string; type: string; count: number }>;
  subjects?: string[];
  selected_subject?: string;
  review_rules?: {
    strict_concepts?: string;
    high_confidence_exposures?: string;
    weak_concepts?: string;
    mistake_due?: string;
    concept_due?: string;
    concept_reviewed?: string;
  };
  due_mistakes?: LearningMistakeSummary[];
  recent_questions?: Array<{
    question: string;
    source: string;
    timestamp: string;
    intent?: string;
    concepts?: Array<{ name: string; confidence?: number }>;
  }>;
}

// Agentic review planning is intentionally hidden until it is integrated into the chat workflow.
const mistakeHref = (id: string, bookName: string) => `/mistakes/${encodeURIComponent(id)}?book_name=${encodeURIComponent(bookName || 'default')}`;

const LearningPage: React.FC = () => {
  const { bookName, setBookName, subject, setSubject } = useChatContext();
  const [books, setBooks] = useState<ScopeBookOption[]>([]);
  const [summary, setSummary] = useState<LearningSummary | null>(null);
  const [subjectFilter, setSubjectFilter] = useState(subject || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reviewMessage, setReviewMessage] = useState('');
  const [reviewError, setReviewError] = useState<{ name: string; text: string } | null>(null);
  const [reviewingConcept, setReviewingConcept] = useState('');
  const [expandedDueId, setExpandedDueId] = useState('');
  const [expandedConcept, setExpandedConcept] = useState('');
  const [visibleCount, setVisibleCount] = useState(5);
  const [showMoreConcepts, setShowMoreConcepts] = useState(false);
  const firstConceptRef = useRef<HTMLButtonElement>(null);
  const [selectedActivityDate, setSelectedActivityDate] = useState('');

  const [kgJob, setKgJob] = useState<{ id: string; status: string; progress?: number; message?: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!bookName) {
      setKgJob(null);
      return () => { cancelled = true; };
    }
    get('/jobs?type=textbook_kg_enhancement&limit=20')
      .then((res) => {
        if (cancelled || !res?.success) return;
        const active = (res.data || []).find((job: { book_name?: string; status?: string }) =>
          job.book_name === bookName && ['queued', 'running', 'cancelling'].includes(job.status || '')
        );
        setKgJob(active || null);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [bookName]);

  useEffect(() => {
    let cancelled = false;
    get('/books/list')
      .then((res) => {
        if (!cancelled && res?.success) setBooks(res.data || []);
      })
      .catch(() => {
        if (!cancelled) setBooks([]);
      });
    const onChanged = () => {
      get('/books/list')
        .then((res) => setBooks(res?.success ? res.data || [] : []))
        .catch(() => setBooks([]));
    };
    window.addEventListener('books:changed', onChanged);
    return () => {
      cancelled = true;
      window.removeEventListener('books:changed', onChanged);
    };
  }, []);

  useEffect(() => {
    setSubjectFilter(subject || '');
  }, [subject]);

  const switchBook = async (name: string) => {
    if (!name) {
      setBookName('');
      setSummary(null);
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
  };

  const updateSubjectFilter = (value: string) => {
    setSubjectFilter(value);
    setSubject(value);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    setReviewMessage('');
    try {
      const params = new URLSearchParams({ book_name: bookName || 'default' });
      if (subjectFilter) params.set('subject', subjectFilter);
      const res = await get(`/kg/learning-summary?${params.toString()}`, 90000);
      if (res?.success) setSummary(res.data);
      else setError(res?.message || '学习情况加载失败');
    } catch (e) {
      setError(e instanceof DOMException && e.name === 'AbortError' ? '学习情况加载超时，请稍后重试或先缩小筛选范围。' : e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [bookName, subjectFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!kgJob?.id || !['queued', 'running', 'cancelling'].includes(kgJob.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const res = await get(`/jobs/${encodeURIComponent(kgJob.id)}`);
        if (res?.success) {
          setKgJob(res.data);
          if (res.data.status === 'completed') await load();
        }
      } catch {
        // Keep the last durable job state; the generic jobs endpoint can resume polling.
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [kgJob?.id, kgJob?.status, load]);

  const kgJobIsRunning = ['queued', 'running', 'cancelling'].includes(kgJob?.status || '');
  const kgJobFailed = ['failed', 'cancelled', 'interrupted'].includes(kgJob?.status || '');

  const startKGEnhancement = async () => {
    if (!bookName || kgJobIsRunning) return;
    setError('');
    try {
      const estimateRes = await get(`/kg/enhance/estimate?book_name=${encodeURIComponent(bookName)}`);
      if (!estimateRes?.success) {
        setError(estimateRes?.message || '\u65e0\u6cd5\u4f30\u7b97\u6982\u5ff5\u7d22\u5f15\u63d0\u53d6\u4efb\u52a1');
        return;
      }
      const estimate = estimateRes.data || {};
      const confirmed = window.confirm(
        `\u6559\u6750\u6982\u5ff5\u7d22\u5f15\u63d0\u53d6\u5c06\u5411\u5df2\u914d\u7f6e\u7684\u5916\u90e8 LLM \u53d1\u9001\u7b5b\u9009\u540e\u7684\u6559\u6750\u7247\u6bb5\u3002\n` +
        `\u9884\u8ba1\u53d1\u9001\u7ea6 ${estimate.selected_characters || 0} \u4e2a\u5b57\u7b26\u3002\n\n` +
        `\u662f\u5426\u7ee7\u7eed\uff1f`
      );
      if (!confirmed) return;
      const res = await post('/kg/enhance', { book_name: bookName, allow_external_llm: true });
      if (!res?.success) {
        setError(res?.message || '\u6982\u5ff5\u7d22\u5f15\u63d0\u53d6\u542f\u52a8\u5931\u8d25');
        return;
      }
      setKgJob({ ...(res.data || {}), id: res.job_id || res.data?.id, status: res.data?.status || 'queued' });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleConceptReview = async (name: string, quality = 4) => {
    setReviewMessage('');
    setReviewError(null);
    setReviewingConcept(name);
    try {
      const res = await post(`/kg/concept-review?book_name=${encodeURIComponent(bookName || 'default')}`, { name, quality });
      if (!res?.success) {
        setReviewError({ name, text: res?.message || '概念复习记录失败，请重试。' });
        return;
      }
      await load();
      setReviewMessage(`已记录「${name}」的概念复习，今天不再提醒`);
    } catch (e) {
      setReviewError({ name, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setReviewingConcept('');
    }
  };

  const subjects = summary?.subjects || [];
  const subjectSuggestions = Array.from(new Set([...subjects, ...books.map((book) => book.subject || '').filter(Boolean)]));
  const dueMistakes = summary?.due_mistakes || [];
  const recommended = summary?.concept_review_plan || [];
  const recommendedNames = new Set(recommended.map((item) => item.name));
  const supplementary = (summary?.review_queue || []).filter((item, index, items) => !recommendedNames.has(item.name) && items.findIndex((candidate) => candidate.name === item.name) === index);
  const primaryCount = dueMistakes.length + recommended.length;
  const shownMistakes = dueMistakes.slice(0, visibleCount);
  const shownConcepts = recommended.slice(0, Math.max(0, visibleCount - dueMistakes.length));
  const todayKey = toDateKey(new Date());
  const weekStart = new Date();
  weekStart.setHours(0, 0, 0, 0);
  weekStart.setDate(weekStart.getDate() - 6);
  const activeDays = (summary?.daily || []).filter((item) => item.date >= toDateKey(weekStart) && item.date <= todayKey && item.total > 0).length;
  const startConcept = () => {
    setVisibleCount(Math.max(visibleCount, dueMistakes.length + 1));
    setExpandedConcept(recommended[0].name);
    window.requestAnimationFrame(() => firstConceptRef.current?.focus());
  };

  return (
    <div className="learning-page management-workspace flex h-full min-w-0 flex-col">
      <div className="app-page-header learning-page-header border-b border-border bg-bg-primary">
        <h2 className="app-page-title">复习计划</h2>
        <Link className="app-secondary-button" to="/goals">目标与任务</Link>
        <div className="window-drag-region" aria-hidden="true" />
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          <ScopeSelector
            subject={subjectFilter}
            bookName={bookName}
            books={books}
            suggestions={subjectSuggestions}
            onSubjectChange={updateSubjectFilter}
            onBookChange={switchBook}
            allowAllSubjects
            align="right"
            width="wide"
            disabled={loading && !books.length}
          />
        </div>
      </div>

      <div className="learning-page-content management-page-content flex-1 overflow-y-auto">
        {loading && <PageState kind="loading" title="正在整理学习情况" description="数据较多时可能需要十几秒。" />}

        {error && !loading && <ActionableIssue title="暂时无法整理复习计划" impact="今天的薄弱点和待复习顺序可能不完整；错题和学习记录不会丢失。" actions={<button onClick={load} className="app-secondary-button">重新加载</button>} details={error} />}
        {!loading && !error && summary && (
          <div className="review-page-body">
            <section className="review-today" aria-labelledby="review-today-title">
              <div className="review-today-main">
                <div>
                  <h3 id="review-today-title" className="workspace-section-heading">今日复习</h3>
                  <p className="review-today-counts"><strong>{summary.mistake_stats.due_today}</strong> 道到期错题 <span aria-hidden="true">·</span> <strong>{recommended.length}</strong> 个本次推荐概念</p>
                  <p className="review-today-context">近期薄弱概念 {summary.stats.weak_count} 个 · 近 7 天活跃 {activeDays} 天</p>
                </div>
                <div className="review-today-actions">
                  {summary.mistake_stats.due_today > 0 ? <Link to="/learning/review" className="app-primary-button">开始本次复习</Link>
                    : recommended.length > 0 ? <button type="button" onClick={startConcept} className="app-primary-button">开始本次复习</button>
                    : supplementary.length > 0 ? <button type="button" onClick={() => setShowMoreConcepts(true)} className="app-primary-button">查看待复习概念</button>
                    : <Link to="/" className="app-primary-button">继续学习</Link>}
                  <span>{summary.mistake_stats.due_today > 0 ? '从到期错题开始' : recommended.length > 0 ? '从首个推荐概念开始' : supplementary.length > 0 ? '查看补充概念' : '今天暂无待复习内容'}</span>
                </div>
              </div>
            </section>

            <section aria-labelledby="review-queue-title">
              <div className="review-section-head">
                <div><h3 id="review-queue-title" className="workspace-section-heading">复习队列</h3>
                  <p className="review-section-copy">先处理到期错题，概念按当前推荐顺序排列。</p></div>
                <button onClick={load} disabled={loading} className="app-ghost-button"><RefreshCw className="h-4 w-4" />刷新</button>
              </div>
              {reviewMessage && <p role="status" className="review-feedback">{reviewMessage}</p>}
              <div className="review-list">
                {primaryCount > 0 ? <>
                  {shownMistakes.length > 0 && <div className="review-group-label">到期错题 <span>{summary.mistake_stats.due_today} 道{summary.mistake_stats.due_today > dueMistakes.length ? ` · 当前返回 ${dueMistakes.length} 道` : ''}</span></div>}
                  {shownMistakes.map((mistake, index) => <MistakePreview key={mistake.id} mistake={mistake} bookName={bookName} index={index + 1} first={index === 0} expanded={expandedDueId === mistake.id} onToggle={() => setExpandedDueId(expandedDueId === mistake.id ? '' : mistake.id)} />)}
                  {shownConcepts.length > 0 && <div className="review-group-label">本次推荐概念 <span>{recommended.length} 个</span></div>}
                  {shownConcepts.map((item, index) => <ConceptReviewCard key={item.name} item={item} bookName={bookName} index={dueMistakes.length + index + 1} first={dueMistakes.length + index === 0} open={expandedConcept === item.name} onToggle={() => setExpandedConcept(expandedConcept === item.name ? '' : item.name)} onReview={handleConceptReview} reviewing={reviewingConcept === item.name} error={reviewError?.name === item.name ? reviewError.text : ''} buttonRef={index === 0 ? firstConceptRef : undefined} />)}
                  {visibleCount < primaryCount && <button type="button" className="review-show-more" onClick={() => setVisibleCount((count) => count + 5)}>显示更多 · 当前展示 {Math.min(visibleCount, primaryCount)} / {primaryCount} 条已返回的主要条目</button>}
                </> : <div className="review-empty">当前没有到期错题或本次推荐概念。{supplementary.length ? '可以查看下方补充概念。' : '继续学习或录入错题后，复习内容会在这里更新。'}</div>}
                {supplementary.length > 0 && <div className="review-supplementary">
                  <button type="button" aria-expanded={showMoreConcepts} onClick={() => setShowMoreConcepts(!showMoreConcepts)} className="review-supplementary-toggle">补充待复习概念 <span>{supplementary.length} 个 {showMoreConcepts ? '收起' : '展开'} <ChevronDown className="h-4 w-4" /></span></button>
                  {showMoreConcepts && supplementary.map((item, index) => <div className="review-row" key={item.name}>
                    <span className="review-index">{primaryCount + index + 1 < 10 ? `0${primaryCount + index + 1}` : primaryCount + index + 1}</span>
                    <div className="review-row-content"><strong>{item.name}</strong><p>{item.reason === 'weak' ? '已标记薄弱' : item.reason === 'forgotten' ? '进入遗忘复习队列' : '进入待复习队列'} · 时间信息未提供</p>{reviewError?.name === item.name && <p role="alert" className="review-row-error">{reviewError.text}</p>}</div>
                    <span className="review-status">待复习</span>
                    <button type="button" className="review-row-action" onClick={() => handleConceptReview(item.name, 4)} disabled={reviewingConcept === item.name}>{reviewingConcept === item.name ? '记录中…' : '标记已复习'}</button>
                  </div>)}
                </div>}
              </div>
              <details className="review-rules"><summary>排序依据</summary><p>到期错题先于本次推荐概念；同组保持现有服务端顺序。补充概念单独列出。</p>{summary.review_rules?.concept_due && <p>{summary.review_rules.concept_due}</p>}</details>
            </section>

            <section className="review-insights" aria-labelledby="review-analysis-title">
              <h3 id="review-analysis-title" className="workspace-section-heading">学习洞察</h3>
              <p className="review-section-copy">用于观察学习模式，不改变今天的行动顺序。</p>
              <div className="review-insight-columns">
                <InsightList title="高频概念" items={summary.top_concepts.map((item) => ({ name: item.name, detail: `${item.count} 次` }))} empty="暂无高频概念" />
                <InsightList title="错题相关薄弱点" items={summary.mistake_weak_points.map((item) => ({ name: item.name, detail: `${item.count} 道` }))} empty="暂无错题薄弱点" />
              </div>
              <div className="review-activity">
                <ActivityHeatmap daily={summary.daily_details || summary.daily.map((item) => ({ ...item, subjects: [] }))} selectedDate={selectedActivityDate} onSelectDate={setSelectedActivityDate} />
                {(summary.recent_questions?.length || 0) > 0 && <div className="review-recent-questions"><h4>最近学习问题</h4>{summary.recent_questions?.slice(0, 5).map((item, index) => <div key={`${item.timestamp}-${index}`}><p>{item.question}</p><span>{item.source === 'mistake' ? '来自错题' : '来自问答'}{item.timestamp ? ` · ${item.timestamp.slice(0, 10)}` : ''}</span></div>)}</div>}
              </div>
              {kgJob && <TaskStatus title="完善知识关联" detail={kgJob.message || kgJob.status} progress={kgJob.progress} state={kgJobFailed ? 'error' : kgJob.status === 'completed' ? 'success' : 'loading'} />}
              {bookName && <button onClick={startKGEnhancement} disabled={kgJobIsRunning} className="app-secondary-button"><BrainCircuit className="h-4 w-4" />{kgJobIsRunning ? '正在完善知识关联' : '完善知识关联'}</button>}
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

const toDateKey = (date: Date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
};

const daysBetweenDateKeys = (later: string, earlier: string) => {
  const toUtc = (key: string) => Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) - 1, Number(key.slice(8, 10)));
  return Math.max(0, Math.round((toUtc(later) - toUtc(earlier)) / 86400000));
};

const heatColor = (total: number) => {
  if (total <= 0) return 'bg-[var(--heat-0-bg)] border-[var(--heat-0-border)]';
  if (total === 1) return 'bg-[var(--heat-1-bg)] border-[var(--heat-1-border)]';
  if (total <= 3) return 'bg-[var(--heat-2-bg)] border-[var(--heat-2-border)]';
  if (total <= 7) return 'bg-[var(--heat-3-bg)] border-[var(--heat-3-border)]';
  return 'bg-[var(--heat-4-bg)] border-[var(--heat-4-border)]';
};

const ActivityHeatmap = ({ daily, selectedDate, onSelectDate }: { daily: DailyDetail[]; selectedDate: string; onSelectDate: (date: string) => void }) => {
  const detailByDate = new Map(daily.map((item) => [item.date, item]));
  const earliest = daily.length ? daily.reduce((min, item) => item.date < min ? item.date : min, daily[0].date) : '';
  const today = new Date();
  const start = new Date(today);
  start.setHours(0, 0, 0, 0);
  start.setDate(today.getDate() - today.getDay() - 77);
  const weeks = Array.from({ length: 12 }, (_, weekIndex) => (
    Array.from({ length: 7 }, (_, dayIndex) => {
      const date = new Date(start);
      date.setDate(start.getDate() + weekIndex * 7 + dayIndex);
      const key = toDateKey(date);
      return { key, detail: detailByDate.get(key) };
    })
  ));
  const latest = [...daily].sort((a, b) => b.date.localeCompare(a.date)).find((item) => item.total > 0)?.date || toDateKey(today);
  const currentDate = selectedDate || latest;
  const current = detailByDate.get(currentDate);

  return (
    <section>
      <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-4">
        <div className="flex items-center gap-2 workspace-interface-text font-medium text-text-primary">
          <CalendarDays className="h-4 w-4 text-accent" /> 最近每日活动
        </div>
        <div className="flex items-center gap-1 text-[11px] text-text-secondary">
          <span>少</span>
          {[0, 1, 3, 7, 10].map((value) => <span key={value} className={`h-3 w-3 rounded-sm border ${heatColor(value)}`} />)}
          <span>多</span>
        </div>
      </div>
      <div className="review-activity-content px-4 pb-4">
        <div className="overflow-x-auto pb-1">
          <div className="grid w-max grid-flow-col grid-rows-7 gap-1">
            {weeks.flatMap((week) => week.map(({ key, detail }) => (
              <button
                key={key}
                type="button"
                onClick={() => onSelectDate(key)}
                title={`${key}：${!earliest || key < earliest || key > toDateKey(today) ? '数据未覆盖' : `${detail?.total || 0} 次`}`}
                className={`h-3.5 w-3.5 shrink-0 box-border rounded-sm border transition-colors hover:brightness-95 active:translate-y-0 active:scale-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${!earliest || key < earliest || key > toDateKey(today) ? 'border-border bg-bg-secondary opacity-40' : heatColor(detail?.total || 0)} ${currentDate === key ? 'ring-2 ring-inset ring-accent' : ''}`}
                aria-label={`${key} 学习活动 ${!earliest || key < earliest || key > toDateKey(today) ? '数据未覆盖' : `${detail?.total || 0} 次`}`}
              />
            )))}
          </div>
        </div>
        <div className="bg-bg-secondary p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="workspace-interface-text font-semibold text-text-primary">{currentDate}</div>
            <div className="workspace-support-text text-text-secondary">{!earliest || currentDate < earliest || currentDate > toDateKey(today) ? '数据未覆盖' : `${current?.total || 0} 次`}</div>
          </div>
          {current ? (
            <div className="space-y-3">
              <p className="workspace-support-text text-text-secondary">问答 {current.qa} · 错题 {current.mistake}</p>
              {current.subjects.length ? current.subjects.map((item) => (
                <div key={item.book_name || item.subject} className="space-y-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
                  <div className="flex items-center justify-between gap-2 workspace-support-text">
                    <span className="truncate font-medium text-text-primary">{item.book_name || item.subject}</span>
                    <span className="flex-shrink-0 text-text-secondary">问答 {item.qa} / 错题 {item.mistake}</span>
                  </div>
                  <p className="workspace-support-text leading-5 text-text-secondary">
                    {item.concepts.length
                      ? `涉及 ${item.concepts.map((concept) => `${concept.name}${concept.count > 1 ? ` ×${concept.count}` : ''}`).join('、')}`
                      : '暂无概念明细'}
                  </p>
                </div>
              )) : <div className="workspace-support-text text-text-secondary">暂无教材概念明细</div>}
            </div>
          ) : (
            <div className="py-6 text-center workspace-support-text text-text-secondary">{!earliest || currentDate < earliest || currentDate > toDateKey(today) ? '该日期未提供数据' : '这一天暂无记录'}</div>
          )}
        </div>
      </div>
    </section>
  );
};
const ConceptReviewCard = ({ item, bookName, index, first, open, onToggle, onReview, reviewing, error, buttonRef }: { item: ConceptReviewCardData; bookName: string; index: number; first: boolean; open: boolean; onToggle: () => void; onReview: (name: string, quality?: number) => void; reviewing?: boolean; error?: string; buttonRef?: React.Ref<HTMLButtonElement> }) => (
  <article className="review-row">
    <span className="review-index">{String(index).padStart(2, '0')}</span>
    <div className="review-row-content">
      <button ref={buttonRef} type="button" aria-expanded={open} onClick={onToggle} className="review-row-title">{item.name} <ChevronDown className={open ? 'h-4 w-4 rotate-180' : 'h-4 w-4'} /></button>
      <p>{first && <span className="review-first">先复习 · </span>}{item.reasons.slice(0, 2).join(' · ') || '当前推荐概念'}</p>
      <p className="review-row-meta">{!item.reasons.some((reason) => reason.includes('上次复习')) && (item.days_since_review == null ? '暂无复习记录' : `距上次复习 ${item.days_since_review} 天`)}{!item.reasons.some((reason) => reason.includes('累计接触')) && item.exposure_count > 0 && ` · 累计接触 ${item.exposure_count} 次`}</p>
      {error && <p role="alert" className="review-row-error">{error}</p>}
      {open && <div className="review-detail">
        {item.reasons.length > 2 && <p>推荐依据：{item.reasons.join('；')}</p>}
        <MiniBlock icon={ClipboardList} title="相关近期问题">{item.recent_questions.length ? item.recent_questions.map((question, i) => <p key={i}>{question.question}{question.mistake_id && <Link to={mistakeHref(question.mistake_id, bookName)}>查看错题</Link>}</p>) : <p>暂无直接关联的近期问题</p>}</MiniBlock>
        <MiniBlock icon={BookOpen} title="教材线索">{item.textbook_snippets.length ? item.textbook_snippets.map((snippet, i) => <p key={i}>{snippet.chapter || snippet.text}</p>) : <p>暂无章节线索</p>}</MiniBlock>
        <MiniBlock icon={ClipboardList} title="相关错题">{item.related_mistakes.length ? item.related_mistakes.slice(0, 4).map((mistake) => <Link key={mistake.id} to={mistakeHref(mistake.id, bookName)}>{mistake.question_text || '查看错题'} <ExternalLink className="inline h-3 w-3" /></Link>) : <p>暂无关联错题</p>}</MiniBlock>
      </div>}
    </div>
    <span className="review-status">{reviewing ? '记录中…' : '待复习'}</span>
    <button disabled={reviewing} type="button" onClick={() => onReview(item.name, 4)} className="review-row-action">标记已复习</button>
  </article>
);

const MiniBlock = ({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) => (
  <div className="review-detail-block"><h4><Icon className="h-4 w-4" />{title}</h4><div>{children}</div></div>
);

const MistakePreview = ({ mistake, bookName, index, first, expanded, onToggle }: { mistake: LearningMistakeSummary; bookName: string; index: number; first: boolean; expanded: boolean; onToggle: () => void }) => {
  const due = mistake.next_review?.slice(0, 10);
  const daysLate = due ? daysBetweenDateKeys(toDateKey(new Date()), due) : 0;
  return <article className="review-row">
    <span className="review-index">{String(index).padStart(2, '0')}</span>
    <div className="review-row-content">
      <button type="button" aria-expanded={expanded} onClick={onToggle} className="review-row-title review-question-title"><span>{mistake.question_text || '题干未提供'}</span><ChevronDown className={expanded ? 'h-4 w-4 rotate-180' : 'h-4 w-4'} /></button>
      <p>{first && <span className="review-first">先复习 · </span>}{due ? daysLate > 0 ? `已逾期 ${daysLate} 天` : '今天到期' : '待复习'}{mistake.chapter ? ` · ${mistake.chapter}` : mistake.source ? ` · ${mistake.source}` : ''}</p>
      {expanded && <div className="review-detail review-question-detail"><ChatMessage role="assistant" content={mistake.question_text || '题干未提供'} linkedConcepts={mistake.linked_concepts || []} /></div>}
    </div>
    <span className="review-status">待复习</span>
    <Link to={mistakeHref(mistake.id, bookName)} className="review-row-action">打开 <ExternalLink className="h-3 w-3" /></Link>
  </article>;
};

const InsightList = ({ title, items, empty }: { title: string; items: Array<{ name: string; detail: string }>; empty: string }) => {
  const [all, setAll] = useState(false);
  return <section><h4>{title}</h4>{items.length ? <>{items.slice(0, all ? undefined : 5).map((item) => <div className="review-insight-item" key={item.name}><span>{item.name}</span><span>{item.detail}</span></div>)}{items.length > 5 && <button type="button" onClick={() => setAll(!all)} className="review-text-button">{all ? '收起' : '查看全部'}</button>}</> : <p className="review-muted">{empty}</p>}</section>;
};

export default LearningPage;
