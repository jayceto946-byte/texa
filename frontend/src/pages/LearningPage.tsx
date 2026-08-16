import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BookOpen,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  ExternalLink,

  HelpCircle,
  RefreshCw,
} from 'lucide-react';
import { get, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import ScopeSelector, { type ScopeBookOption } from '../components/ScopeSelector';
import { PageState, StatusBanner, TaskStatus } from '../components/ui/AsyncState';
import { useChatContext } from '../contexts/ChatContext';
import type { ConceptCandidate, ReviewHistoryItem } from '../types';

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
const mistakeHref = (id: string) => `/mistakes?mistake_id=${encodeURIComponent(id)}`;

const LearningPage: React.FC = () => {
  const { bookName, setBookName, subject, setSubject } = useChatContext();
  const [books, setBooks] = useState<ScopeBookOption[]>([]);
  const [summary, setSummary] = useState<LearningSummary | null>(null);
  const [subjectFilter, setSubjectFilter] = useState(subject || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reviewMessage, setReviewMessage] = useState('');
  const [reviewingConcept, setReviewingConcept] = useState('');
  const [expandedDueId, setExpandedDueId] = useState('');
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
    setReviewingConcept(name);
    try {
      const res = await post(`/kg/concept-review?book_name=${encodeURIComponent(bookName || 'default')}`, { name, quality });
      if (!res?.success) {
        setReviewMessage(res?.message || '概念复习记录失败');
        return;
      }
      await load();
      setReviewMessage(`已记录「${name}」的概念复习，今天不再提醒`);
    } catch (e) {
      setReviewMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setReviewingConcept('');
    }
  };

  const subjects = summary?.subjects || [];
  const subjectSuggestions = Array.from(new Set([...subjects, ...books.map((book) => book.subject || '').filter(Boolean)]));

  return (
    <div className="learning-page flex h-full min-w-0 flex-col">
      <div className="app-page-header learning-page-header border-b border-border bg-bg-primary">
        <h2 className="app-page-title">复习计划</h2>
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
          <button
            onClick={load}
            disabled={loading}
            className="review-toolbar-button app-secondary-button"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            onClick={startKGEnhancement}
            disabled={!bookName || kgJobIsRunning}
            className="review-toolbar-button app-secondary-button"
          >
            <BrainCircuit className={`h-4 w-4 ${kgJobIsRunning ? 'animate-pulse' : ''}`} />
            {kgJobIsRunning ? (kgJob?.status === 'cancelling' ? '正在终止知识关联' : '正在完善知识关联') : '完善知识关联'}
          </button>
        </div>
      </div>

      <div className="learning-page-content flex-1 overflow-y-auto p-6">
        {loading && <PageState kind="loading" title="正在整理学习情况" description="数据较多时可能需要十几秒。" />}

        {kgJob && <TaskStatus title="完善知识关联" detail={kgJob.message || kgJob.status} progress={kgJob.progress} state={kgJobFailed ? 'error' : kgJob.status === 'completed' ? 'success' : 'loading'} />}

        {error && !loading && <StatusBanner kind="error" title="学习情况加载失败" description={error} action={<button onClick={load} className="app-secondary-button">重试</button>} />}
        {!loading && !error && summary && (
          <div className="mx-auto max-w-6xl space-y-8">
            <section aria-labelledby="review-today-title">
              <div className="mb-4">
                <h3 id="review-today-title" className="type-section-title text-text-primary">今天要做什么</h3>
                <p className="mt-1 type-caption text-text-secondary">先处理到期错题，再复习由近期薄弱记录触发的概念。</p>
              </div>
              <div className="review-summary grid grid-cols-1 gap-4 border-b border-border pb-5 md:grid-cols-3 md:gap-0 md:divide-x md:divide-border">
                <SummaryFact icon={CalendarDays} label="到期错题" value={summary.mistake_stats.due_today} unit="道" tone="accent" help={summary.review_rules?.mistake_due} emphasis />
                <SummaryFact icon={AlertTriangle} label="近期薄弱概念" value={summary.stats.weak_count} unit="个" tone="warn" help={summary.weak_concepts?.slice(0, 2).map((item) => item.name).join('、') || summary.review_rules?.weak_concepts} />
                <SummaryFact icon={Activity} label="近 7 天有学习记录" value={summary.daily.slice(-7).filter((item) => item.total > 0).length} unit="天" help="按有学习记录的天数统计" />
              </div>

              {reviewMessage && <div className="mt-4 border-l-2 border-[var(--success)] px-3 py-2 text-sm text-[var(--success-text)]">{reviewMessage}</div>}

              <div className="learning-review-sections mt-3 divide-y divide-border border-y border-border">
                <ExpandableSection title="优先复习错题" count={summary.due_mistakes?.length || 0} defaultOpen={Boolean(summary.due_mistakes?.length)}>
                <div className="divide-y divide-border">
                  {summary.due_mistakes?.length ? (
                    summary.due_mistakes.map((mistake) => (
                      <MistakePreview
                        key={mistake.id}
                        mistake={mistake}
                        expanded={expandedDueId === mistake.id}
                        onToggle={() => setExpandedDueId(expandedDueId === mistake.id ? '' : mistake.id)}
                      />
                    ))
                  ) : (
                    <Empty text="当前没有到期错题" compact />
                  )}
                </div>
                </ExpandableSection>

                <ExpandableSection title="优先复习概念" count={summary.concept_review_plan?.length || 0} defaultOpen>
                <div className="learning-concept-grid grid grid-cols-1 gap-x-6 xl:grid-cols-2">
                  {summary.concept_review_plan?.length ? (
                    summary.concept_review_plan.map((item) => (
                      <ConceptReviewCard key={item.name} item={item} onReview={handleConceptReview} reviewing={reviewingConcept === item.name} />
                    ))
                  ) : (
                    <div className="xl:col-span-2"><Empty text="暂无需要优先复习的概念" compact /></div>
                  )}
                </div>
                </ExpandableSection>

                <ExpandableSection title="更多待复习概念" count={summary.review_queue.length}>
                <div className="divide-y divide-border">
                  {summary.review_queue.length ? (
                    summary.review_queue.map((item) => (
                      <div key={item.name} className="flex items-center justify-between px-1 py-3 text-sm">
                        <span className="truncate text-text-primary">{item.name}</span>
                        <span className="ml-3 text-xs text-text-secondary">{item.reason === 'weak' ? '薄弱' : '遗忘'}</span>
                      </div>
                    ))
                  ) : (
                    <Empty text="暂无待复习概念" compact />
                  )}
                </div>
                </ExpandableSection>
              </div>
            </section>

            <section aria-labelledby="review-reason-title">
              <div className="mb-3">
                <h3 id="review-reason-title" className="type-section-title text-text-primary">为什么这些内容优先</h3>
                <p className="mt-1 type-caption text-text-secondary">近期问答、错题关联与遗忘间隔共同决定本次顺序。</p>
              </div>
              <div className="divide-y divide-border border-y border-border">
                <ExpandableSection title="近期问题" count={summary.recent_questions?.length || 0}>
                  <div className="divide-y divide-border">
                    {summary.recent_questions?.length ? (
                      summary.recent_questions.map((item, index) => (
                        <div key={`${item.timestamp}-${index}`} className="space-y-1 py-3">
                          <p className="text-sm leading-6 text-text-primary">{item.question}</p>
                          <p className="type-caption text-text-secondary">
                            {item.source === 'mistake' ? '来自错题' : '来自问答'}
                            {item.timestamp ? ` · ${item.timestamp.slice(0, 10)}` : ''}
                            {item.concepts?.length ? ` · 关联 ${item.concepts.map((concept) => concept.name).join('、')}` : ''}
                          </p>
                        </div>
                      ))
                    ) : <Empty text="暂无问答记录" compact />}
                  </div>
                </ExpandableSection>
              </div>
            </section>

            <section aria-labelledby="review-analysis-title">
              <div className="mb-3">
                <h3 id="review-analysis-title" className="type-section-title text-text-primary">补充分析</h3>
                <p className="mt-1 type-caption text-text-secondary">用于观察长期模式，不改变今天的行动顺序。</p>
              </div>
              <div className="learning-insights grid grid-cols-1 divide-y divide-border border-y border-border xl:grid-cols-3 xl:divide-x xl:divide-y-0">
                <Panel title="高频概念">
                {summary.top_concepts.length ? (
                  summary.top_concepts.map((item) => (
                    <RankRow key={item.name} name={item.name} detail={`${item.count} 次`} />
                  ))
                ) : (
                  <Empty text="暂无高置信概念" compact />
                )}
                </Panel>
                <Panel title="错题相关薄弱点">
                {summary.mistake_weak_points.length ? (
                  summary.mistake_weak_points.map((item) => (
                    <RankRow key={`${item.type}-${item.name}`} name={item.name} detail={`${item.count} 道`} />
                  ))
                ) : (
                  <Empty text="暂无错题薄弱点" compact />
                )}
                </Panel>
                <ActivityHeatmap
                daily={summary.daily_details || summary.daily.map((item) => ({ ...item, subjects: [] }))}
                selectedDate={selectedActivityDate}
                onSelectDate={setSelectedActivityDate}
                />
              </div>
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

const heatColor = (total: number) => {
  if (total <= 0) return 'bg-[#f5f5f7] border-[#e0e0e0]';
  if (total === 1) return 'bg-[#dceeff] border-[#b8dcff]';
  if (total <= 3) return 'bg-[#a8d4ff] border-[#7dbdff]';
  if (total <= 7) return 'bg-[#3f97e8] border-[#237fca]';
  return 'bg-[#0066cc] border-[#0057ad]';
};

const ActivityHeatmap = ({ daily, selectedDate, onSelectDate }: { daily: DailyDetail[]; selectedDate: string; onSelectDate: (date: string) => void }) => {
  const detailByDate = new Map(daily.map((item) => [item.date, item]));
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
  const latest = daily.find((item) => item.total > 0)?.date || toDateKey(today);
  const currentDate = selectedDate || latest;
  const current = detailByDate.get(currentDate);

  return (
    <section>
      <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-4">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <CalendarDays className="h-4 w-4 text-accent" /> 最近每日活动
        </div>
        <div className="flex items-center gap-1 text-[11px] text-text-secondary">
          <span>少</span>
          {[0, 1, 3, 7, 10].map((value) => <span key={value} className={`h-3 w-3 rounded-sm border ${heatColor(value)}`} />)}
          <span>多</span>
        </div>
      </div>
      <div className="space-y-4 px-4 pb-4">
        <div className="overflow-x-auto pb-1">
          <div className="grid w-max grid-flow-col grid-rows-7 gap-1">
            {weeks.flatMap((week) => week.map(({ key, detail }) => (
              <button
                key={key}
                type="button"
                onClick={() => onSelectDate(key)}
                title={`${key}：${detail?.total || 0} 次`}
                className={`h-3.5 w-3.5 shrink-0 box-border rounded-sm border transition-colors hover:brightness-95 active:translate-y-0 active:scale-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${heatColor(detail?.total || 0)} ${currentDate === key ? 'ring-2 ring-inset ring-accent' : ''}`}
                aria-label={`${key} 学习活动 ${detail?.total || 0} 次`}
              />
            )))}
          </div>
        </div>
        <div className="bg-bg-secondary p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-text-primary">{currentDate}</div>
            <div className="text-xs text-text-secondary">{current?.total || 0} 次</div>
          </div>
          {current ? (
            <div className="space-y-3">
              <p className="text-xs text-text-secondary">问答 {current.qa} · 错题 {current.mistake}</p>
              {current.subjects.length ? current.subjects.map((item) => (
                <div key={item.book_name || item.subject} className="space-y-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate font-medium text-text-primary">{item.book_name || item.subject}</span>
                    <span className="flex-shrink-0 text-text-secondary">问答 {item.qa} / 错题 {item.mistake}</span>
                  </div>
                  <p className="text-xs leading-5 text-text-secondary">
                    {item.concepts.length
                      ? `涉及 ${item.concepts.map((concept) => `${concept.name}${concept.count > 1 ? ` ×${concept.count}` : ''}`).join('、')}`
                      : '暂无概念明细'}
                  </p>
                </div>
              )) : <div className="text-xs text-text-secondary">暂无教材概念明细</div>}
            </div>
          ) : (
            <div className="py-6 text-center text-xs text-text-secondary">这一天暂无记录</div>
          )}
        </div>
      </div>
    </section>
  );
};
const ConceptReviewCard = ({ item, onReview, reviewing }: { item: ConceptReviewCardData; onReview: (name: string, quality?: number) => void; reviewing?: boolean }) => {
  const [open, setOpen] = useState(false);
  const linkedMistakes = item.related_mistakes.slice(0, 4);

  return (
    <article className="concept-review-card border-b border-border py-3 last:border-b-0 sm:py-4">
      <div className="flex items-start justify-between gap-2 sm:gap-3">
        <button type="button" onClick={() => setOpen(!open)} className="min-w-0 flex-1 text-left">
          <div className="flex min-w-0 items-center justify-start gap-2">
            {open ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4 text-text-secondary" />}
            <BrainCircuit className={`h-4 w-4 ${item.weak ? 'text-[#9f3f2e]' : 'text-accent'}`} />
            <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-text-primary">{item.name}</h3>
          </div>
          {item.reasons.length > 0 && <p className="mt-2 pl-6 text-xs leading-5 text-text-secondary">{item.reasons.join('；')}</p>}
        </button>
        <button disabled={reviewing} onClick={() => onReview(item.name, 4)} className="flex h-8 flex-shrink-0 items-center gap-1.5 whitespace-nowrap rounded border border-border px-2.5 py-1 text-xs text-text-primary hover:border-accent hover:text-accent disabled:cursor-wait disabled:opacity-60">
          <CheckCircle2 className="h-3.5 w-3.5" /> {reviewing ? '记录中…' : '已复习'}
        </button>
      </div>

      {open && (
        <div className="mt-4 grid gap-4 border-l border-border pl-4 text-sm md:grid-cols-2">
          <MiniBlock icon={BookOpen} title="教材线索">
            {item.textbook_snippets.length ? item.textbook_snippets.map((snippet, index) => (
              <p key={`${snippet.type}-${index}`} className="text-xs leading-5 text-text-secondary">{snippet.chapter || snippet.text}</p>
            )) : <p className="text-xs text-text-secondary">暂无章节线索</p>}
          </MiniBlock>
          <MiniBlock icon={ClipboardList} title="相关错题">
            {item.related_mistakes.length ? (
              <div className="space-y-2">
                <p className="text-xs leading-5 text-text-secondary">已关联 {item.related_mistakes.length} 道错题，题目内容在错题本中查看。</p>
                <div className="flex flex-wrap gap-2">
                  {linkedMistakes.map((mistake) => (
                    <Link key={mistake.id} to={mistakeHref(mistake.id)} className="inline-flex items-center gap-1 rounded border border-border bg-bg-primary px-2 py-1 text-xs text-accent-hover hover:border-accent hover:text-accent">
                      {mistake.id} <ExternalLink className="h-3 w-3" />
                    </Link>
                  ))}
                  <Link to="/mistakes" className="inline-flex items-center gap-1 rounded border border-border bg-bg-primary px-2 py-1 text-xs text-text-primary hover:border-accent hover:text-accent">
                    打开错题本 <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
              </div>
            ) : <p className="text-xs text-text-secondary">暂无关联错题</p>}
          </MiniBlock>
        </div>
      )}
    </article>
  );
};

const MiniBlock = ({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) => (
  <div>
    <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-text-primary"><Icon className="h-3.5 w-3.5 text-accent" />{title}</div>
    <div className="space-y-2">{children}</div>
  </div>
);

const MistakePreview = ({ mistake, expanded, onToggle }: { mistake: LearningMistakeSummary; expanded: boolean; onToggle: () => void }) => (
  <div className="py-3">
    <button type="button" onClick={onToggle} className="flex w-full items-start justify-between gap-3 text-left">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          {expanded ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4 text-text-secondary" />}
          <span className="truncate">{mistake.source || mistake.subject || mistake.id}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-text-secondary">
          {mistake.subject && <span>{mistake.subject}</span>}
          {mistake.chapter && <span>{mistake.chapter}</span>}
          {mistake.next_review && <span>到期 {mistake.next_review}</span>}
        </div>
      </div>
      <Link to={mistakeHref(mistake.id)} onClick={(e) => e.stopPropagation()} className="inline-flex flex-shrink-0 items-center gap-1 text-xs text-accent-hover hover:text-accent">
        打开 <ExternalLink className="h-3 w-3" />
      </Link>
    </button>
    {expanded && (
      <div className="mt-3 bg-bg-secondary p-3">
        <ChatMessage role="assistant" content={mistake.question_text || mistake.id} linkedConcepts={mistake.linked_concepts || []} />
      </div>
    )}
  </div>
);

const SummaryFact = ({ icon: Icon, label, value, unit, tone = 'normal', help, emphasis = false }: { icon: React.ElementType; label: string; value: number; unit: string; tone?: 'normal' | 'warn' | 'accent'; help?: string; emphasis?: boolean }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative px-0 md:px-5 md:first:pl-0">
      <div className="flex items-start justify-between gap-2 sm:gap-3">
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <Icon className={tone === 'warn' ? 'h-4 w-4 text-[#9f3f2e]' : tone === 'accent' ? 'h-4 w-4 text-accent' : 'h-4 w-4'} />
          {label}
        </div>
        {help && (
          <button onClick={() => setOpen(!open)} className="rounded p-0.5 text-text-secondary hover:text-accent" title="复习标准">
            <HelpCircle className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className={`mt-2 font-semibold text-text-primary ${emphasis ? 'text-2xl' : 'text-lg'}`}>{value ?? 0}<span className="ml-1 text-sm font-normal text-text-secondary">{unit}</span></div>
      {help && open && (
        <div className="app-popover-enter absolute right-3 top-9 z-20 w-[min(340px,calc(100vw-88px))] rounded-xl border border-border bg-bg-primary p-3 text-xs">
          <RuleItem title={`${label}的判定`} text={help} />
        </div>
      )}
    </div>
  );
};

const RuleItem = ({ title, text }: { title: string; text: string }) => (
  <div className="space-y-1 border-b border-border py-2 last:border-b-0 last:pb-0 first:pt-0">
    <div className="font-semibold text-text-primary">{title}</div>
    <p className="leading-5 text-text-secondary">{text}</p>
  </div>
);

const Header = ({ title, count, open, onToggle }: { title: string; count?: number; open?: boolean; onToggle?: () => void }) => (
  <button type="button" onClick={onToggle} className="flex w-full items-center justify-between py-3 text-left text-sm font-medium text-text-primary hover:text-accent">
    <span className="flex items-center gap-2">
      {open ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4 text-text-secondary" />}
      {title}
    </span>
    {typeof count === 'number' && <span className="text-xs font-normal text-text-secondary">{count}</span>}
  </button>
);

const ExpandableSection = ({ title, count, defaultOpen = false, children }: { title: string; count?: number; defaultOpen?: boolean; children: React.ReactNode }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section>
      <Header title={title} count={count} open={open} onToggle={() => setOpen(!open)} />
      {open && <div className="mb-3 ml-6 border-l border-border pl-4">{children}</div>}
    </section>
  );
};

const Panel = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section>
    <div className="px-4 pb-2 pt-4 text-sm font-medium text-text-primary">{title}</div>
    <div className="space-y-2 px-4 pb-4">{children}</div>
  </section>
);

const RankRow = ({ name, detail }: { name: string; detail: string }) => (
  <div className="flex items-center justify-between gap-3 text-sm">
    <span className="truncate text-text-primary">{name}</span>
    <span className="flex-shrink-0 text-xs text-text-secondary">{detail}</span>
  </div>
);

const Empty = ({ text, compact = false }: { text: string; compact?: boolean }) => (
  <div className={`text-center text-sm text-text-secondary ${compact ? 'py-3' : 'py-8'}`}>{text}</div>
);

export default LearningPage;
