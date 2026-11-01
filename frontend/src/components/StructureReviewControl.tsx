import { useEffect, useRef, useState } from 'react';
import { get, post } from '../api/client';
import Dialog from './ui/Dialog';
import './structureReview.css';

type Target = { kind: 'book' | 'import' | 'file'; reference: string; book_name: string };
type Report = { model?: string; text_corrections?: number; merged_questions?: number; retained_answer_blocks?: number; changed_headings?: number; outline_changed?: boolean; estimated_cost_cny?: number | null; unresolved?: unknown[]; usage_unknown?: boolean; needs_retry?: boolean };
type Job = { id: string; status: string; message: string; progress: number; result?: { source_id?: string; report?: Report } };
type Plan = { model: string; model_label?: string; provider: string; ready: boolean; pages: number[]; source_characters: number; includes_answer_file: boolean; estimated_cost: { low: number; high: number } | null; max_cost_cny: number };

export function StructureReviewControl({ target, disabled, compact = false, candidateCount, onDispatch, onComplete, onBusyChange }: { target: Target; disabled?: boolean; compact?: boolean; candidateCount?: number; onDispatch?: () => void; onComplete: (result: Job['result']) => void | Promise<void>; onBusyChange?: (busy: boolean) => void }) {
  const key = `texa:structure-review:${target.kind}:${target.reference}`;
  const [jobId, setJobId] = useState(() => localStorage.getItem(key) || '');
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [stopping, setStopping] = useState(false);
  const dispatchLock = useRef(false);
  const [retrying, setRetrying] = useState(() => localStorage.getItem(key + ':failed') === '1');
  const done = useRef(onComplete);
  useEffect(() => { done.current = onComplete; }, [onComplete]);
  const busy = starting || Boolean(jobId);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const payload = await get(`/jobs/${encodeURIComponent(jobId)}`);
        if (!active) return;
        if (!payload.success) throw new Error(payload.message || '整理任务不存在');
        const next = payload.data as Job;
        setJob(next);
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(next.status)) {
          if (next.status === 'completed') {
            await done.current(next.result);
            const retry = Boolean(next.result?.report?.needs_retry);
            setRetrying(retry);
            if (retry) localStorage.setItem(key + ':failed', '1'); else localStorage.removeItem(key + ':failed');
          }
          else { if (next.status !== 'cancelled') setError(next.message); setRetrying(true); localStorage.setItem(key + ':failed', '1'); }
          setStopping(false);
          localStorage.removeItem(key); setJobId('');
        } else timer = setTimeout(poll, 1200);
      } catch (cause) {
        if (active) { setError(cause instanceof Error ? cause.message : String(cause)); timer = setTimeout(poll, 4000); }
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [jobId, key]);
  const purpose = target.kind === 'file' ? 'exercises' : 'textbook';
  const prepare = async () => {
    setConfirmOpen(true); setPlanning(true); setError(''); setPlan(null);
    try {
      const response = await post('/structure-reviews/plan', { ...target, purpose });
      if (!response.success) throw new Error(response.message || '无法估算整理费用');
      setPlan(response.data as Plan);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setPlanning(false); }
  };
  const start = async (purpose: 'outline' | 'exercises' | 'textbook') => {
    if (dispatchLock.current) return;
    dispatchLock.current = true;
    setConfirmOpen(false); setStarting(true); setError(''); setJob(null); setStopping(false); onDispatch?.();
    try {
      const payload = await post('/structure-reviews', { ...target, purpose, retry_failed: retrying });
      if (!payload.success) throw new Error(payload.message || '无法启动智能整理');
      localStorage.setItem(key, payload.data.id); setJob(payload.data); setJobId(payload.data.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setStarting(false); dispatchLock.current = false; }
  };
  const stop = async () => {
    setStopping(true);
    try { await post(`/jobs/${jobId}/cancel`, {}); }
    catch { setStopping(false); setError('停止请求未送达，请重试'); }
  };
  const report = job?.result?.report;
  const summary = report ? [report.outline_changed === false ? '目录无需调整' : report.changed_headings ? `调整 ${report.changed_headings} 处目录` : '',
    report.text_corrections ? `校正 ${report.text_corrections} 处文字` : '', report.merged_questions ? `合并 ${report.merged_questions} 道重复题` : '',
    report.retained_answer_blocks ? `保留 ${report.retained_answer_blocks} 个解答片段` : ''].filter(Boolean).join('，') : '';
  return <section className={`structure-review-control${compact ? ' is-compact' : ''}`} aria-label="智能整理">
    <div className="structure-review-row">
      <button type="button" className="app-secondary-button" title={summary || undefined} disabled={busy || disabled || planning} onClick={() => void prepare()}>{compact ? (busy ? `整理中 ${job?.progress || 0}%` : retrying ? '重试整理' : '智能整理') : retrying ? '重试智能整理' : target.kind === 'file' ? '智能整理题目与答案' : '智能校正目录与文字'}</button>
      {!compact && <span role="status">{busy ? `${job?.message || '正在准备整理'}${job ? ` · ${job.progress}%` : ''}` : summary || job?.message || (target.kind === 'file' ? '校正识别文字，配对原书答案，合并重复题。' : '结合全书标题与目录，自动更新下方结果。')}</span>}
      {busy && jobId && <button type="button" className="app-secondary-button" disabled={stopping} onClick={() => void stop()}>{stopping ? '正在停止' : '停止'}</button>}
    </div>
    {!compact && retrying && !busy && <p className="structure-review-hint">复用已完成结果，只重试未完成部分。{report?.usage_unknown ? '上次部分请求结果未知，重试可能再次计费。' : ''}</p>}
    {!compact && report && <details className="structure-review-receipt"><summary>处理记录{report.estimated_cost_cny != null ? ` · 估算 ¥${report.estimated_cost_cny.toFixed(4)}` : ''}</summary><div className="structure-review-record"><p>{report.model} · {job?.status === 'completed' ? `${report.unresolved?.length || 0} 项仍需核对` : '本次未完成，已知用量已保留'}。{report.usage_unknown ? '费用包含未知请求的预留，' : ''}实际以服务商账单为准。</p></div></details>}
    {error && !confirmOpen && <p role="alert" className="structure-review-error">{error}</p>}
    <Dialog open={confirmOpen} title="确认智能整理" onClose={() => setConfirmOpen(false)} dismissOnBackdrop className="structure-review-confirm">
      <h2>{target.kind === 'file' ? '整理全部题目？' : '校正教材？'}</h2>
      {planning ? <p role="status">正在估算范围与费用…</p> : plan && <>
        <dl><div><dt>处理范围</dt><dd>{target.kind === 'file' ? (candidateCount != null ? `全部 ${candidateCount} 道题` : '全部题目') : '本次导入的教材'}，{plan.pages.length} 页{plan.includes_answer_file ? '，含独立答案文件' : ''}</dd></div>
        <div><dt>使用模型</dt><dd>{plan.model_label || plan.model}</dd></div>
        <div><dt>预估费用</dt><dd>{plan.estimated_cost ? `约 ¥${plan.estimated_cost.low.toFixed(2)}–¥${plan.estimated_cost.high.toFixed(2)}` : '当前模型暂无可用单价，无法自动估算'}</dd></div></dl>
        <p>{target.kind === 'file' ? '将题目和相关图片发送给该模型整理。' : '将教材文字和相关图片发送给该模型校正。'}{plan.estimated_cost ? `最多花费 ¥${plan.max_cost_cny}。` : ''}可随时停止，已发送的部分仍可能收费。</p>
        {!plan.ready && <p role="alert">请先到设置中配置识图模型。</p>}
      </>}
      {error && <p role="alert">{error}</p>}
      <footer><button className="app-secondary-button" onClick={() => setConfirmOpen(false)}>取消</button><button className="app-primary-button" disabled={!plan?.ready || planning || starting} onClick={() => void start(purpose)}>开始整理</button></footer>
    </Dialog>
  </section>;
}
