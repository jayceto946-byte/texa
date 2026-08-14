import React, { useEffect, useMemo, useState } from 'react';
import { BookOpen, BrainCircuit, Check, ChevronRight, Circle, Database, Image, Loader2, Sparkles, Wrench, X } from 'lucide-react';

import type { ActivityKind, ChatActivity } from '../../types';
import { activityDuration, completedActivityCount } from '../../utils/chatActivities';

const icons: Record<ActivityKind, React.ComponentType<{ className?: string }>> = {
  analysis: BrainCircuit,
  tool: Wrench,
  evidence: BookOpen,
  reasoning: Sparkles,
  generation: Sparkles,
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

  const active = activities.find((item) => item.status === 'active');
  const failed = activities.find((item) => item.status === 'failed');
  const settled = completedActivityCount(activities);
  const duration = activityDuration(activities);
  const summary = failed
    ? `处理遇到问题 · ${failed.label}`
    : active
      ? active.label
      : `已完成 ${settled || activities.length} 个步骤${duration ? ` · ${durationLabel(duration)}` : ''}`;
  const metaUncertainties = useMemo(() => activities.flatMap((item) => {
    const raw = item.meta?.uncertainties;
    return Array.isArray(raw) ? raw.map(String) : [];
  }).slice(0, 5), [activities]);

  if (!activities.length) return null;
  return (
    <section className="mb-3 overflow-hidden rounded-xl border border-border bg-[var(--surface-subtle)]">
      <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        {failed ? <X className="h-4 w-4 text-[var(--danger)]" /> : active ? <Loader2 className="h-4 w-4 animate-spin text-accent" /> : <Check className="h-4 w-4 text-[var(--success)]" />}
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-text-primary">{summary}</span>
        <ChevronRight className={`h-3.5 w-3.5 text-text-secondary transition-transform ${expanded ? 'rotate-90' : ''}`} />
      </button>
      {expanded && (
        <div className="space-y-0.5 border-t border-border px-3 py-2">
          {activities.map((item) => {
            const Icon = icons[item.kind];
            return (
              <div key={item.id} className="grid grid-cols-[16px_18px_minmax(0,1fr)_auto] gap-1.5 py-1.5">
                <StatusIcon status={item.status} />
                <Icon className="mt-0.5 h-3.5 w-3.5 text-text-secondary" />
                <div className="min-w-0">
                  <div className={`text-xs font-medium ${item.status === 'failed' ? 'text-[var(--danger)]' : 'text-text-primary'}`}>{item.label}</div>
                  {item.detail && <div className="mt-0.5 text-[11px] leading-4 text-text-secondary">{item.detail}</div>}
                </div>
                {item.duration_ms ? <span className="pt-0.5 text-[10px] text-text-tertiary">{durationLabel(item.duration_ms)}</span> : null}
              </div>
            );
          })}
          {metaUncertainties.length > 0 && (
            <div className="mt-1 rounded-lg border border-amber-300/50 bg-amber-50/60 px-2.5 py-2 text-[11px] leading-4 text-amber-900">
              视觉不确定项：{metaUncertainties.join('；')}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default ExecutionTrace;
