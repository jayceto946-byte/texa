import React from 'react';
import { AlertCircle, CheckCircle2, CircleAlert, Info, Loader2 } from 'lucide-react';

export type AsyncStateKind = 'loading' | 'empty' | 'error' | 'success' | 'info';

const meta = {
  loading: { icon: Loader2, className: 'border-border bg-bg-card text-text-secondary', iconClass: 'animate-spin text-accent' },
  empty: { icon: Info, className: 'border-border bg-bg-card text-text-secondary', iconClass: 'text-text-secondary' },
  error: { icon: AlertCircle, className: 'border-[var(--danger-border)] bg-[var(--danger-bg)] text-[var(--danger-text)]', iconClass: 'text-[var(--danger)]' },
  success: { icon: CheckCircle2, className: 'border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success-text)]', iconClass: 'text-[var(--success)]' },
  info: { icon: CircleAlert, className: 'border-border bg-[var(--accent-softer)] text-text-secondary', iconClass: 'text-accent' },
} as const;

export function StatusBanner({ kind = 'info', title, description, action }: { kind?: AsyncStateKind; title: string; description?: string; action?: React.ReactNode }) {
  const item = meta[kind];
  const Icon = item.icon;
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${item.className}`}>
      <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${item.iconClass}`} />
      <div className="min-w-0 flex-1">
        <div className="type-control">{title}</div>
        {description && <p className="type-caption mt-0.5 leading-5 opacity-85">{description}</p>}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}

export function PageState({ kind, title, description, action }: { kind: AsyncStateKind; title: string; description?: string; action?: React.ReactNode }) {
  if (kind === 'loading') {
    return (
      <div role="status" aria-label={title} className="app-panel space-y-3 p-5">
        <div className="h-4 w-32 animate-pulse rounded bg-border/70" />
        <div className="h-3 w-full max-w-md animate-pulse rounded bg-border/45" />
        <div className="h-3 w-3/4 max-w-sm animate-pulse rounded bg-border/45" />
      </div>
    );
  }
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className="app-panel px-5 py-8 text-center">
      <StatusBanner kind={kind} title={title} description={description} action={action} />
    </div>
  );
}

export function TaskStatus({ title, detail, progress, state = 'loading' }: { title: string; detail?: string; progress?: number; state?: 'loading' | 'success' | 'error' }) {
  const value = typeof progress === 'number' ? Math.max(0, Math.min(100, progress)) : null;
  const item = meta[state];
  const Icon = item.icon;
  return (
    <div className={`border-y px-4 py-3 ${item.className}`} role={state === 'error' ? 'alert' : 'status'}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${item.iconClass}`} />
        <div className="min-w-0 flex-1">
          <div className="type-control">{title}</div>
          {detail && <p className="type-caption mt-0.5 leading-5 opacity-85">{detail}</p>}
        </div>
      </div>
      {value !== null && (
        <div className="mt-3">
          <div className="mb-1 flex justify-between type-caption text-text-secondary"><span>任务进度</span><span>{Math.round(value)}%</span></div>
          <div className="h-1 overflow-hidden bg-bg-primary"><div className="h-full bg-accent transition-[width]" style={{ width: `${value}%` }} /></div>
        </div>
      )}
    </div>
  );
}

export function ActionableIssue({
  title,
  impact,
  actions,
  details,
  kind = 'error',
}: {
  title: string;
  impact: string;
  actions: React.ReactNode;
  details?: React.ReactNode;
  kind?: 'error' | 'info';
}) {
  const item = meta[kind];
  const Icon = item.icon;
  return (
    <section role={kind === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-3 py-3 ${item.className}`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${item.iconClass}`} />
        <div className="min-w-0 flex-1">
          <h3 className="type-control text-text-primary">{title}</h3>
          <p className="type-caption mt-1 leading-5 opacity-90">{impact}</p>
          <div className="mt-3 flex flex-wrap gap-2">{actions}</div>
          {details && <details className="mt-3 type-caption opacity-80"><summary className="cursor-pointer">详细信息</summary><div className="mt-1 break-words leading-5">{details}</div></details>}
        </div>
      </div>
    </section>
  );
}
