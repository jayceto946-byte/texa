import React, { useState } from 'react';
import type { ChatReportCard, LearningReport } from '../../types';
import { useLearningNoteFont } from '../../hooks/useLearningNoteFont';

const reportMetrics = [
  ['问答', 'qa_count'],
  ['新错题', 'new_mistakes'],
  ['复习错题', 'reviewed_mistakes'],
  ['新习题', 'new_exercises'],
  ['练习', 'practiced_exercises'],
  ['概念接触', 'concept_exposures'],
] as const;

const ReportList = ({ title, items, empty }: { title: string; items: string[]; empty: string }) => (
  <section>
    <div className="mb-2 text-xs font-medium text-text-secondary">{title}</div>
    <div className="space-y-2">
      {items.length ? items.map((item, index) => <div key={`${item}-${index}`} className="rounded-lg border border-border bg-[var(--surface-subtle)] px-3 py-2 text-sm text-text-primary">{item}</div>) : <div className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-sm text-text-secondary">{empty}</div>}
    </div>
  </section>
);

const ReportCard: React.FC<{ card: ChatReportCard }> = ({ card }) => {
  useLearningNoteFont();
  const [open, setOpen] = useState(false);
  const report: LearningReport = card.report;
  const title = card.kind === 'daily' ? '学习日报' : '学习周报';
  const summary = report.summary || {};
  const topConceptText = report.top_concepts?.length ? report.top_concepts.slice(0, 3).map((item) => item.name).join('、') : '暂无概念记录';
  const weakText = report.weak_points?.length ? report.weak_points.slice(0, 3).map((item) => item.name).join('、') : '暂无新增薄弱点';

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-border bg-[var(--surface-subtle)] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-text-primary">{title}</div>
            <div className="mt-1 text-xs text-text-secondary">{report.start_date} 至 {report.end_date} · {report.book_name}</div>
          </div>
          <button type="button" onClick={() => setOpen((value) => !value)} className="rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs text-text-primary transition-colors hover:border-accent/50 hover:text-accent">
            {open ? '收起完整情况' : '展开完整情况'}
          </button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {reportMetrics.map(([label, key]) => (
            <div key={key} className="rounded-lg border border-border bg-bg-card px-3 py-2">
              <div className="text-lg font-semibold text-text-primary">{summary[key] || 0}</div>
              <div className="text-[11px] text-text-secondary">{label}</div>
            </div>
          ))}
        </div>

        <div className="mt-4 grid gap-2 text-sm md:grid-cols-2">
          <div className="rounded-lg border border-border bg-bg-card px-3 py-2">
            <div className="mb-1 text-xs font-medium text-text-secondary">高频概念</div>
            <div className="text-text-primary">{topConceptText}</div>
          </div>
          <div className="rounded-lg border border-border bg-bg-card px-3 py-2">
            <div className="mb-1 text-xs font-medium text-text-secondary">薄弱点</div>
            <div className="text-text-primary">{weakText}</div>
          </div>
        </div>

        {report.suggestions?.length > 0 && (
          <div className="learning-note mt-3 rounded-lg border border-accent/20 bg-[var(--accent-softer)] px-3 py-2 text-sm text-text-primary">{report.suggestions[0]}</div>
        )}
      </div>

      {open && (
        <div className="space-y-3 rounded-xl border border-border bg-bg-card p-4">
          <div className="grid gap-3 md:grid-cols-3">
            <ReportList title="高频概念" items={(report.top_concepts || []).map((item) => `${item.name} · ${item.count}`)} empty="暂无概念记录" />
            <ReportList title="薄弱点" items={(report.weak_points || []).map((item) => `${item.name} · ${item.count}`)} empty="暂无新增错题薄弱点" />
            <ReportList title={card.kind === 'daily' ? '今日建议' : '下周建议'} items={report.suggestions || []} empty="暂无建议" />
          </div>
          <div>
            <div className="mb-2 text-xs font-medium text-text-secondary">最近提问</div>
            <div className="space-y-2">
              {(report.recent_questions || []).length ? report.recent_questions.map((item, idx) => (
                <div key={`${item.time}-${idx}`} className="rounded-lg border border-border bg-[var(--surface-subtle)] px-3 py-2 text-sm">
                  <div className="mb-1 text-[11px] text-text-secondary">{item.time}</div>
                  <div className="text-text-primary">{item.question}</div>
                </div>
              )) : <div className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-sm text-text-secondary">暂无问答记录</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ReportCard;