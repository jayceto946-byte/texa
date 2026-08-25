import { useMemo, useState } from 'react';
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, ChevronRight, Clock3, Database, FileText, ShieldCheck } from 'lucide-react';
import type { AgentPendingAction, ChatAgentCard } from '../../types';
import { resolveAgentAction } from '../../api/client';
import { MarkdownMessage } from './MarkdownMessage';

const toolLabels: Record<string, string> = {
  search_textbook: '教材',
  search_concepts: '概念',
  find_textbook_examples: '教材例题',
  link_concepts: '关联',
  get_due_mistakes: '到期错题',
  get_mistake_stats: '错题统计',
  get_weak_concepts: '薄弱概念',
  search_exercises: '习题筛选',
  get_recent_progress: '最近进度',
  build_review_plan: '复习计划',
  propose_add_mistake: '待确认错题',
  propose_concept_review: '待确认复习',
  propose_practice_session: '练习提案',
};

const pendingActionLabels: Record<string, string> = {
  add_mistake: '加入错题本',
  mark_concept_reviewed: '记录概念复习',
  create_practice_session: '创建练习会话',
};

function compactData(value: unknown) {
  if (!value || typeof value !== 'object') return '';
  const data = value as Record<string, unknown>;
  if (Array.isArray(data.snippets)) return `${data.snippets.length} 条片段`;
  if (Array.isArray(data.concepts)) return `${data.concepts.length} 个概念`;
  if (Array.isArray(data.examples)) return `${data.examples.length} 道教材例题`;
  if (Array.isArray(data.mistakes)) return `${data.mistakes.length} 道错题`;
  if (Array.isArray(data.weak_concepts)) return `${data.weak_concepts.length} 个薄弱概念`;
  if (Array.isArray(data.exercises)) return `${data.exercises.length} 道习题`;
  if (Array.isArray(data.recent_events)) return `${data.recent_events.length} 条近期记录`;
  if (Array.isArray(data.plan)) return `${data.plan.length} 项`;
  if (data.stats && typeof data.stats === 'object') return '统计已读取';
  if (data.preview) return '等待确认';
  return '';
}

export default function AgentResultCard({ card }: { card: ChatAgentCard }) {
  const [open, setOpen] = useState(false);
  const [actions, setActions] = useState<AgentPendingAction[]>(() => card.response.summary.pending_actions || []);
  const [resolvingId, setResolvingId] = useState('');
  const [actionError, setActionError] = useState('');
  const { response } = card;
  const successfulTools = response.tool_outputs.filter((item) => item.result.success);
  const failedTools = response.tool_outputs.filter((item) => !item.result.success);
  const pendingActions = actions;
  const executionTrace = response.execution_trace;
  const synthesisStatus = executionTrace?.synthesis.status;
  const chips = useMemo(() => (
    successfulTools.map((item) => {
      const detail = compactData(item.result.data);
      const timing = item.timing ? `${item.timing.elapsed_ms} ms` : '';
      return {
        name: item.tool,
        label: toolLabels[item.tool] || item.tool,
        detail: [detail, timing].filter(Boolean).join(' · '),
      };
    })
  ), [successfulTools]);

  const resolveAction = async (action: AgentPendingAction, decision: 'confirm' | 'reject') => {
    if (!action.action_id || resolvingId) return;
    setResolvingId(action.action_id);
    setActionError('');
    try {
      const resolved = await resolveAgentAction(action.action_id, decision);
      setActions((current) => current.map((item) => (
        item.action_id === resolved.action.action_id ? resolved.action : item
      )));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '操作未完成，请重试');
    } finally {
      setResolvingId('');
    }
  };

  return (
    <article className="agent-result-card overflow-hidden rounded-xl border border-border bg-bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[var(--surface-black)] text-white">
            <Bot className="h-3.5 w-3.5" />
          </span>
          <span className="truncate text-sm font-semibold text-text-primary">学习工具</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="status-success inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs">
            <ShieldCheck className="h-3 w-3" />
            只读
          </span>
          {executionTrace && (
            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-bg-primary px-2 py-0.5 text-xs text-text-secondary">
              <Clock3 className="h-3 w-3" />
              {(executionTrace.total_elapsed_ms / 1000).toFixed(1)} 秒
            </span>
          )}
          {(synthesisStatus === 'timeout' || synthesisStatus === 'error') && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-300/70 bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
              <AlertTriangle className="h-3 w-3" />
              {synthesisStatus === 'timeout' ? '总结超时' : '总结失败'}
            </span>
          )}
          {pendingActions.length > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-accent/25 bg-[var(--accent-softer)] px-2 py-0.5 text-xs text-accent-hover">
              <CheckCircle2 className="h-3 w-3" />
              {pendingActions.length} 项待确认
            </span>
          )}
          {failedTools.length > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-300/70 bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
              <AlertTriangle className="h-3 w-3" />
              {failedTools.length} 项不可用
            </span>
          )}
        </div>
      </div>

      <div className="px-3 py-3">
        {response.answer ? (
          <MarkdownMessage content={response.answer} />
        ) : (
          <div className="text-sm text-text-secondary">工具已执行，暂无生成总结。</div>
        )}
      </div>

      {pendingActions.length > 0 && (
        <div className="border-t border-border px-3 py-2.5">
          <div className="mb-1.5 text-xs font-medium text-text-primary">待确认操作</div>
          <div className="space-y-1.5">
            {pendingActions.map((action, index) => (
              <div key={action.action_id || `${action.type}-${index}`} className="flex items-center justify-between gap-3 rounded-lg bg-[var(--accent-softer)] px-2.5 py-2 text-xs">
                <span className="text-text-primary">{pendingActionLabels[action.type] || action.type}</span>
                {(!action.status || action.status === 'pending') ? (
                  <span className="flex flex-shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      disabled={!action.action_id || Boolean(resolvingId)}
                      onClick={() => void resolveAction(action, 'reject')}
                      className="rounded-md px-2 py-1 text-text-secondary hover:text-text-primary disabled:opacity-50"
                    >
                      暂不执行
                    </button>
                    <button
                      type="button"
                      disabled={!action.action_id || Boolean(resolvingId)}
                      onClick={() => void resolveAction(action, 'confirm')}
                      className="rounded-md bg-accent px-2 py-1 font-medium text-white hover:bg-accent-hover disabled:opacity-50"
                    >
                      {resolvingId === action.action_id ? '执行中…' : '确认执行'}
                    </button>
                  </span>
                ) : (
                  <span className="flex-shrink-0 text-text-secondary">
                    {action.status === 'confirmed' ? '已执行' : action.status === 'rejected' ? '已取消' : '执行失败'}
                  </span>
                )}
              </div>
            ))}
          </div>
          {actionError && <div className="mt-2 text-xs text-red-600">{actionError}</div>}
        </div>
      )}

      {chips.length > 0 && (
        <div className="border-t border-border px-3 py-2">
          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="flex w-full items-center justify-between gap-3 text-left text-xs text-text-secondary transition-colors hover:text-text-primary"
          >
            <span className="inline-flex items-center gap-1.5">
              {open ? <ChevronDown className="h-3.5 w-3.5 text-accent" /> : <ChevronRight className="h-3.5 w-3.5" />}
              证据
            </span>
            <span>{chips.length}</span>
          </button>

          {open && (
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {chips.map((chip) => (
                <div key={`${chip.name}-${chip.detail}`} className="flex items-center gap-2 rounded-lg border border-border bg-bg-primary px-2.5 py-2 text-xs">
                  {chip.name === 'search_textbook' ? <FileText className="h-3.5 w-3.5 text-accent" /> : <Database className="h-3.5 w-3.5 text-accent" />}
                  <span className="font-medium text-text-primary">{chip.label}</span>
                  {chip.detail && <span className="min-w-0 truncate text-text-secondary">{chip.detail}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
