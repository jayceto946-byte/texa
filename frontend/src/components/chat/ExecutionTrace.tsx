import React, { useEffect, useId, useState } from 'react';
import { BookOpen, BrainCircuit, Check, ChevronRight, Circle, Database, Image, Loader2, MessageSquareText, Wrench, X, Pause, AlertCircle } from 'lucide-react';

import type { ActivityKind, AssistantSource, ChatActivity } from '../../types';
import { activityDuration } from '../../utils/chatActivities';
import { MarkdownMessage } from './MarkdownMessage';
import './ExecutionTrace.css';

const icons: Record<ActivityKind, React.ComponentType<{ className?: string }>> = {
  analysis: BrainCircuit, tool: Wrench, evidence: BookOpen, reasoning: BrainCircuit,
  generation: MessageSquareText, memory: Database, system: Image,
};
const statusLabels = { active: '进行中', completed: '完成', failed: '失败', skipped: '跳过', pending: '等待' };
const inputLabels: Record<string, string> = {
  query: '查询', book_name: '教材', subject: '学科', chapter: '章节', operation: '运算',
  expression: '表达式', variable: '变量', lower: '下限', upper: '上限', kind: '校验方式',
  original: '原式', candidate: '待校验结果', left: '左式', right: '右式', days: '天数', limit: '数量', tag: '标签', status: '状态',
};
function durationLabel(value: number) {
  return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} 秒`;
}
function stringValue(value: unknown) { return typeof value === 'string' ? value : ''; }
function strings(value: unknown) { return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []; }
function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}; }

const StatusIcon: React.FC<{ status: ChatActivity['status'] }> = ({ status }) => {
  if (status === 'active') return <Loader2 className="animate-spin text-accent" />;
  if (status === 'completed') return <Check className="text-[var(--success)]" />;
  if (status === 'failed') return <X className="text-[var(--danger)]" />;
  return <Circle className="text-text-tertiary" />;
};

function EvidenceList({ items, count, scope, onInspectSources }: { items: unknown[]; count?: number; scope?: string; onInspectSources?: () => void }) {
  return <div className="execution-evidence">
    <div className="execution-detail-heading">
      <span>{scope === 'answer' ? '交给回答生成的教材证据' : '检索到的教材段落'} · {count ?? items.length} 段</span>
      {onInspectSources && <button type="button" onClick={onInspectSources}>查看来源定位</button>}
    </div>
    {items.map((raw, index) => {
      const item = record(raw);
      const path = strings(item.section_path).join(' › ') || stringValue(item.section_title) || stringValue(item.chapter);
      const page = typeof item.page_idx === 'number' && item.page_idx >= 0 ? `第 ${item.page_idx + 1} 页` : '页码未记录';
      const preview = stringValue(item.preview) || stringValue(item.text);
      return <details className="execution-source" key={`${item.chunk_id || item.id || index}`}>
        <summary><BookOpen /><span><strong>{stringValue(item.book_name) || '教材来源'}</strong><small>{[stringValue(item.id), path, page].filter(Boolean).join(' · ')}</small></span><ChevronRight className="execution-disclosure" /></summary>
        <div className="execution-source-text">
          {preview ? <MarkdownMessage content={`${preview}${item.truncated ? '…' : ''}`} disableRemoteMedia /> : <p className="execution-muted">这条历史记录没有保存段落预览，可查看已有来源定位。</p>}
          {item.truncated === true && <small>片段预览已截短</small>}
          {Boolean(item.chunk_id) && <small>段落：{stringValue(item.chunk_id)}{item.index_version ? ` · 索引：${stringValue(item.index_version)}` : ''}</small>}
        </div>
      </details>;
    })}
    {(count || 0) > items.length && <p className="execution-muted">展示前 {items.length} 段预览，共 {count} 段。</p>}
  </div>;
}

function ActivityDetails({ item, onInspectSources }: { item: ChatActivity; onInspectSources?: () => void }) {
  const meta = item.meta || {};
  const inputs = record(meta.input_preview);
  const evidence = Array.isArray(meta.evidence_previews) ? meta.evidence_previews : [];
  const missing = strings(meta.missing_required_outputs);
  const warnings = strings(meta.warnings);
  const uncertainties = strings(meta.uncertainties);
  const chapters = strings(meta.chapters);
  const result = stringValue(meta.result_preview);
  const tool = stringValue(meta.tool) || stringValue(meta.tool_id);
  const required = Array.isArray(meta.required_outputs) ? meta.required_outputs.map(record).map((output) => stringValue(output.label)).filter(Boolean) : [];
  return <div className="execution-step-detail">
    {item.detail && item.detail !== item.label && <p>{item.detail}</p>}
    {chapters.length > 0 && <p>回答范围：{chapters.join('、')}</p>}
    {required.length > 0 && <p>本轮回答要求：{required.join('；')}</p>}
    {tool && <p className="execution-muted">工具：{tool}{meta.provenance ? ` · 来源：${stringValue(meta.provenance)}` : ''}</p>}
    {Object.keys(inputs).length > 0 && <dl>{Object.entries(inputs).filter(([key]) => inputLabels[key]).map(([key, value]) => <React.Fragment key={key}><dt>{inputLabels[key]}</dt><dd>{String(value)}</dd></React.Fragment>)}</dl>}
    {result && <div className="execution-tool-result"><span>返回结果</span><p>{result}</p></div>}
    {typeof meta.verification_passed === 'boolean' && <p>工具校验：{meta.verification_passed ? '通过' : '未通过'}</p>}
    {missing.length > 0 && <p className="execution-warning">缺少必要输出：{missing.join('、')}</p>}
    {warnings.length > 0 && <p className="execution-warning">{warnings.join('；')}</p>}
    {uncertainties.length > 0 && <p className="execution-warning">识别不确定项：{uncertainties.join('；')}</p>}
    {evidence.length > 0 && <EvidenceList items={evidence} count={Number(meta.evidence_count) || evidence.length} scope={stringValue(meta.evidence_scope)} onInspectSources={onInspectSources} />}
    {typeof meta.verification_status === 'string' && <p>回答校验：{meta.verification_status === 'passed' ? '通过发布门槛' : '未通过或尚无法核验'}</p>}
  </div>;
}

const ExecutionTrace: React.FC<{ activities: ChatActivity[]; stage?: string; sources?: AssistantSource[]; taskStatus?: string; onInspectSources?: () => void }> = ({ activities, stage, sources = [], taskStatus, onInspectSources }) => {
  const terminal = ['done', 'error', 'stopped', 'waiting_for_input', 'waiting_for_confirmation'].includes(stage || '');
  const [expanded, setExpanded] = useState(false);
  const detailId = useId();
  useEffect(() => { setExpanded(false); }, [terminal]);
  // The reducer retains operation insertion order; completion seq must not reorder work.
  const visible = activities.filter((item) => item.id !== 'transport' && item.id !== 'execute' && item.event_type !== 'output_delta');
  const active = [...activities].reverse().find((item) => item.status === 'active');
  const failed = visible.some((item) => item.status === 'failed');
  const degraded = taskStatus === 'degraded';
  const duration = activityDuration(activities);
  const [clock, setClock] = useState({ baseline: 0, delta: 0 });
  useEffect(() => {
    if (terminal) return;
    const receivedAt = Date.now();
    const timer = window.setInterval(() => setClock({ baseline: duration, delta: Date.now() - receivedAt }), 1000);
    return () => window.clearInterval(timer);
  }, [terminal, duration]);
  const displayedDuration = duration + (!terminal && clock.baseline === duration ? clock.delta : 0);
  const hasEvidence = visible.some((item) => Array.isArray(item.meta?.evidence_previews) && item.meta.evidence_previews.length > 0);
  const title = terminal
    ? stage === 'stopped' ? '已停止' : stage === 'error' ? '回答中断' : stage === 'waiting_for_input' ? '等待补充输入' : taskStatus === 'waiting_for_confirmation' ? '等待确认' : degraded ? '回答待核验' : failed ? '处理结束 · 有步骤失败' : '已完成'
    : active?.label || '正在处理';
  const HeaderIcon = !terminal ? Loader2 : stage === 'stopped' ? Pause : stage === 'error' ? X : degraded || failed || stage === 'waiting_for_input' ? AlertCircle : Check;
  const recent = visible.filter((item) => item.status !== 'active' && item.id !== active?.id).slice(-2);

  if (!activities.length) return null;
  return <section className={`execution-trace ${terminal ? 'is-terminal' : 'is-running'}`} aria-label="任务执行过程">
    <button type="button" className="execution-trace-toggle" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} aria-controls={detailId}>
      <HeaderIcon className={!terminal ? 'animate-spin text-accent' : stage === 'error' ? 'text-[var(--danger)]' : degraded || failed ? 'text-[var(--warning)]' : 'text-text-secondary'} />
      <span className="execution-title" role="status" aria-live="polite">{title}</span>
      {displayedDuration > 0 && <span className="execution-time">{durationLabel(displayedDuration)}</span>}
      <span className="execution-toggle-label">{expanded ? '收起过程' : '查看过程'}</span>
      <ChevronRight className={`execution-disclosure ${expanded ? 'is-open' : ''}`} />
    </button>
    {!terminal && !expanded && <div className="execution-live-preview">
      {active?.detail && <p>{active.detail}</p>}
      {recent.map((item) => <div key={item.id}><StatusIcon status={item.status} /><span>{item.label}</span>{item.duration_ms !== undefined && <small>{durationLabel(item.duration_ms)}</small>}</div>)}
    </div>}
    {expanded && <div id={detailId} className="execution-trace-body">
      <p className="execution-public-note">处理摘要、教材证据与工具回执</p>
      <ol className="execution-steps">
        {visible.map((item) => {
          const Icon = icons[item.kind];
          return <li key={item.id} className={`execution-step is-${item.status}`}>
            <div className="execution-step-heading"><StatusIcon status={item.status} /><Icon /><span>{item.label}</span><small>{statusLabels[item.status]}{item.duration_ms !== undefined ? ` · ${durationLabel(item.duration_ms)}` : ''}</small></div>
            <ActivityDetails item={item} onInspectSources={onInspectSources} />
          </li>;
        })}
      </ol>
      {!hasEvidence && sources.length > 0 && <EvidenceList items={sources} scope="answer" onInspectSources={onInspectSources} />}
    </div>}
  </section>;
};
export default ExecutionTrace;
