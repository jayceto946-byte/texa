import React, { useCallback, useEffect, useState } from 'react';
import { BarChart3, BookOpen, ClipboardCheck, HelpCircle, Loader2, RefreshCw } from 'lucide-react';
import { get } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import { useLearningNoteFont } from '../hooks/useLearningNoteFont';

type WeeklyReport = {
  book_name: string;
  subject: string;
  start_date: string;
  end_date: string;
  summary: Record<string, number>;
  top_concepts: { name: string; count: number }[];
  weak_points: { name: string; count: number }[];
  recent_questions: { time: string; question: string }[];
  suggestions: string[];
};

const Metric: React.FC<{ label: string; value: number; compact?: boolean }> = ({ label, value, compact = false }) => (
  <div className={`rounded-md border border-border bg-bg-card ${compact ? 'p-3' : 'p-4'}`}>
    <div className={`${compact ? 'text-xl' : 'text-2xl'} font-semibold text-text-primary`}>{value}</div>
    <div className="mt-1 text-xs text-text-secondary">{label}</div>
  </div>
);

export const LearningReportPanel: React.FC<{ days?: number; compact?: boolean }> = ({ days = 7, compact = false }) => {
  useLearningNoteFont();
  const { bookName, subject } = useChatContext();
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const title = days <= 1 ? '学习日报' : '学习周报';
  const suggestionTitle = days <= 1 ? '今日建议' : '下周建议';

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ book_name: bookName || 'default', subject, days: String(days) });
      const res = await get(`/reports/weekly?${params.toString()}`);
      if (!res.success) throw new Error(res.message || `生成${title}失败`);
      setReport(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [bookName, days, subject, title]);

  useEffect(() => { loadReport(); }, [loadReport]);

  const summary = report?.summary || {};

  return (
    <div className={compact ? 'space-y-4' : 'h-full overflow-y-auto bg-bg-primary p-6'}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-bg-card">
            <BarChart3 className="h-5 w-5 text-accent" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
          </div>
        </div>
        <button onClick={loadReport} disabled={loading} className="flex items-center gap-2 rounded-md border border-border bg-bg-card px-3 py-2 text-sm hover:bg-bg-primary disabled:opacity-50">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {loading && !report && (
        <div className="flex items-center justify-center gap-2 rounded-md border border-border bg-bg-card py-8 text-sm text-text-secondary">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在整理{title}
        </div>
      )}

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {(!loading || report) && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <Metric label="问答次数" value={summary.qa_count || 0} compact={compact} />
            <Metric label="新增错题" value={summary.new_mistakes || 0} compact={compact} />
            <Metric label="复习错题" value={summary.reviewed_mistakes || 0} compact={compact} />
            <Metric label="新增习题" value={summary.new_exercises || 0} compact={compact} />
            <Metric label="练习习题" value={summary.practiced_exercises || 0} compact={compact} />
            <Metric label="概念接触" value={summary.concept_exposures || 0} compact={compact} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <section className="rounded-md border border-border bg-bg-card p-4">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><BookOpen className="h-4 w-4 text-accent" /> 高频概念</h3>
              <div className="space-y-2">
                {(report?.top_concepts || []).length ? report!.top_concepts.map((item) => (
                  <div key={item.name} className="flex justify-between rounded-md bg-bg-primary px-3 py-2 text-sm"><span>{item.name}</span><span className="text-text-secondary">{item.count}</span></div>
                )) : <div className="text-sm text-text-secondary">暂无概念记录</div>}
              </div>
            </section>

            <section className="rounded-md border border-border bg-bg-card p-4">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><ClipboardCheck className="h-4 w-4 text-accent" /> 薄弱点</h3>
              <div className="space-y-2">
                {(report?.weak_points || []).length ? report!.weak_points.map((item) => (
                  <div key={item.name} className="flex justify-between rounded-md bg-bg-primary px-3 py-2 text-sm"><span>{item.name}</span><span className="text-text-secondary">{item.count}</span></div>
                )) : <div className="text-sm text-text-secondary">暂无新增错题薄弱点</div>}
              </div>
            </section>

            <section className="rounded-md border border-border bg-bg-card p-4">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><HelpCircle className="h-4 w-4 text-accent" /> {suggestionTitle}</h3>
              <div className="space-y-2">
                {(report?.suggestions || []).map((item, idx) => <div key={idx} className="learning-note rounded-md bg-bg-primary px-3 py-2 text-sm text-text-primary">{item}</div>)}
              </div>
            </section>
          </div>

          <section className="rounded-md border border-border bg-bg-card p-4">
            <h3 className="mb-3 text-sm font-semibold">最近提问</h3>
            <div className="space-y-2">
              {(report?.recent_questions || []).length ? report!.recent_questions.map((item, idx) => (
                <div key={`${item.time}-${idx}`} className="rounded-md bg-bg-primary px-3 py-2 text-sm">
                  <div className="mb-1 text-xs text-text-secondary">{item.time}</div>
                  <div>{item.question}</div>
                </div>
              )) : <div className="text-sm text-text-secondary">暂无问答记录</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
};

const WeeklyReportPage: React.FC = () => <LearningReportPanel />;

export default WeeklyReportPage;
