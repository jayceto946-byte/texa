import React, { useEffect, useMemo, useState } from 'react';
import { BookOpen, BrainCircuit, Check, ChevronRight, Circle, Database, Image, Loader2, MessageSquareText, Wrench, X } from 'lucide-react';

import type { ActivityKind, ChatActivity } from '../../types';
import { activityDuration, completedActivityCount } from '../../utils/chatActivities';

const icons: Record<ActivityKind, React.ComponentType<{ className?: string }>> = {
  analysis: BrainCircuit,
  tool: Wrench,
  evidence: BookOpen,
  reasoning: BrainCircuit,
  generation: MessageSquareText,
  memory: Database,
  system: Image,
};

function durationLabel(value: number) {
  if (!value) return '';
  return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} 秒`;
}

const StatusIcon: React.FC<{ status: ChatActivity['status'] }> = ({ status }) => {
  if (status === 'active') return <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />;
  if (status === 'completed') return <Check className="h-3.5 w-3.5 text-[var(--success)]" />;
  if (status === 'failed') return <X className="h-3.5 w-3.5 text-[var(--danger)]" />;
  return <Circle className={`h-3 w-3 ${status === 'skipped' ? 'text-text-tertiary' : 'text-border'}`} />;
};

const ExecutionTrace: React.FC<{ activities: ChatActivity[]; stage?: string }> = ({ activities, stage }) => {
  const terminal = stage === 'done' || stage === 'error' || stage === 'stopped';
  const [expanded, setExpanded] = useState(!terminal);
  useEffect(() => {
    if (terminal) setExpanded(false);
    else setExpanded(true);
  }, [terminal]);

  const active = [...activities]
    .filter((item) => item.status === 'active')
    .sort((left, right) => (right.seq || 0) - (left.seq || 0))[0];
  const failed = activities.find((item) => item.status === 'failed');
  const settled = completedActivityCount(activities);
  const duration = activityDuration(activities);
  const orderedActivities = useMemo(() => [...activities].sort((left, right) => (
    (left.seq ?? Number.MAX_SAFE_INTEGER) - (right.seq ?? Number.MAX_SAFE_INTEGER)
  )), [activities]);
  const activeWaitMs = Number(active?.meta?.waited_ms || active?.elapsed_ms || 0);
  const summary = failed
    ? `处理遇到问题 · ${failed.label}`
    : active
      ? active.detail || active.label
      : `查看执行过程 · ${settled || activities.length} 项事件${duration ? ` · ${durationLabel(duration)}` : ''}`;
  const metaUncertainties = useMemo(() => activities.flatMap((item) => {
    const raw = item.meta?.uncertainties;
    return Array.isArray(raw) ? raw.map(String) : [];
  }).slice(0, 5), [activities]);

  if (!activities.length) return null;
  return (
    <section className="mb-4" aria-label="任务执行过程">
      {terminal ? (
        <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} className="flex items-center gap-1.5 py-0.5 text-left text-[11px] leading-4 text-text-secondary hover:text-text-primary">
          {failed ? <X className="h-3 w-3 text-[var(--danger)]" /> : <Check className="h-3 w-3 text-[var(--success)]" />}
          <span>{summary}</span>
          <ChevronRight className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`} />
        </button>
      ) : (
        <div className="flex items-start gap-2 py-1" role="status" aria-live="polite">
          <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
          <div className="min-w-0 flex-1">
            <div className="text-sm leading-5 text-text-primary">{summary}</div>
            {activeWaitMs >= 1000 ? (
              <div className="mt-0.5 text-[11px] text-text-tertiary">当前操作已等待 {durationLabel(activeWaitMs)}</div>
            ) : null}
          </div>
        </div>
      )}
      {expanded && (
        <div className="ml-[7px] mt-1 space-y-0.5 border-l border-border pl-4" role="log" aria-live={terminal ? 'off' : 'polite'}>
          {orderedActivities.map((item) => {
            const Icon = icons[item.kind];
            return (
              <div key={item.id} className="grid grid-cols-[16px_18px_minmax(0,1fr)_auto] gap-1.5 py-1.5">
                <StatusIcon status={item.status} />
                <Icon className="mt-0.5 h-3.5 w-3.5 text-text-secondary" />
                <div className="min-w-0">
                  <div className={`text-xs ${item.status === 'active' ? 'font-medium text-text-primary' : item.status === 'failed' ? 'font-medium text-[var(--danger)]' : 'text-text-secondary'}`}>{item.label}</div>
                  {item.detail && item.detail !== item.label && <div className="mt-0.5 text-[11px] leading-4 text-text-tertiary">{item.detail}</div>}
                </div>
                {item.status === 'active' && Number(item.meta?.waited_ms || item.elapsed_ms || 0) >= 1000
                  ? <span className="pt-0.5 text-[10px] text-text-tertiary">{durationLabel(Number(item.meta?.waited_ms || item.elapsed_ms || 0))}</span>
                  : item.duration_ms
                    ? <span className="pt-0.5 text-[10px] text-text-tertiary">{durationLabel(item.duration_ms)}</span>
                    : null}
              </div>
            );
          })}
          {metaUncertainties.length > 0 && (
            <div className="mt-1 border-l-2 border-amber-400 pl-2.5 text-[11px] leading-4 text-amber-900">
              视觉不确定项：{metaUncertainties.join('；')}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default ExecutionTrace;
