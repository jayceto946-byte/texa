import { useEffect, useRef, useState } from 'react';
import { apiFetch, get, post } from '../api/client';
import Selector from './ui/Selector';
import './structureReview.css';

type Target = { kind: 'book' | 'import' | 'file'; reference: string; book_name: string };
type Plan = { pages: number[]; candidate_pages: number; total_pages: number; max_calls: number; model: string; ready: boolean; has_original_pages: boolean; image_scope: string; notice: string };
type Job = { id: string; status: string; message: string; progress: number; result?: { source_id?: string; report?: { status: string } } };

export function StructureReviewControl({ target, disabled, onComplete, onBusyChange }: { target: Target; disabled?: boolean; onComplete: (result: Job['result']) => void | Promise<void>; onBusyChange?: (busy: boolean) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [mode, setMode] = useState('suspect');
  const [maxPages, setMaxPages] = useState(24);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [pdf, setPdf] = useState<File | null>(null);
  const [inputPrice, setInputPrice] = useState('');
  const [outputPrice, setOutputPrice] = useState('');
  const [maxCost, setMaxCost] = useState(1);
  const key = `texa:structure-review:${target.kind}:${target.reference}`;
  const [jobId, setJobId] = useState(() => localStorage.getItem(key) || '');
  const done = useRef(onComplete);
  useEffect(() => { done.current = onComplete; }, [onComplete]);
  const pending = loading || Boolean(jobId);
  useEffect(() => { onBusyChange?.(pending); return () => onBusyChange?.(false); }, [pending, onBusyChange]);
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const payload = await get(`/jobs/${encodeURIComponent(jobId)}`);
        if (!active) return;
        if (!payload.success) throw new Error(payload.message || '审阅任务不存在');
        const next = payload.data as Job; setJob(next);
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(next.status)) {
          localStorage.removeItem(key); setJobId('');
          if (next.status === 'completed') await done.current(next.result);
          else setError(next.message);
        } else timer = setTimeout(poll, 1200);
      } catch (cause) {
        if (active) { setError(cause instanceof Error ? cause.message : String(cause)); timer = setTimeout(poll, 4000); }
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [jobId, key]);
  const inspect = async () => {
    setLoading(true); setError('');
    try { const data = await post('/structure-reviews/plan', { ...target, mode, max_pages: maxPages }); setPlan(data.data); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setLoading(false); }
  };
  const start = async () => {
    setLoading(true); setError('');
    try {
      const data = await post('/structure-reviews', { ...target, mode, max_pages: maxPages, max_cost_cny: maxCost, input_price: Number(inputPrice), output_price: Number(outputPrice) });
      if (!data.success) throw new Error(data.message || '无法启动审阅');
      localStorage.setItem(key, data.data.id); setJob(data.data); setJobId(data.data.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setLoading(false); }
  };
  const associatePdf = async () => {
    if (!pdf) return;
    setLoading(true); setError('');
    try {
      const form = new FormData(); form.append('file', pdf);
      Object.entries(target).forEach(([name, value]) => form.append(name, value));
      const response = await apiFetch('/structure-reviews/source-pdf', { method: 'POST', body: form }, 120000);
      const payload = await response.json();
      if (!response.ok || !payload.success) throw new Error(payload.detail || payload.message || '关联原页失败');
      setPlan(null); setPdf(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setLoading(false); }
  };
  return <section className="structure-review-control" aria-label="视觉结构审阅">
    <div className="structure-review-row"><button type="button" className="app-secondary-button" aria-expanded={expanded} disabled={disabled && !pending} onClick={() => setExpanded(!expanded)}>视觉辅助校正</button>{job && <span role="status">{job.message}{pending ? ` · ${job.progress}%` : ''}</span>}{pending && jobId && <button type="button" className="app-ghost-button" onClick={() => void post(`/jobs/${jobId}/cancel`, {}).catch(() => setError('停止请求未送达，请重试'))}>停止</button>}</div>
    {expanded && <>
      <div className="structure-review-row"><Selector ariaLabel="视觉审阅范围" value={mode} onChange={value => { setMode(value); setPlan(null); }} options={[{ value: 'suspect', label: '疑难页与覆盖抽查' }, { value: 'all', label: '逐页审阅' }]} disabled={pending || disabled} /><label>本次最多页数<input aria-label="视觉审阅页数上限" type="number" min={1} max={1000} value={maxPages} disabled={pending || disabled} onChange={e => { setMaxPages(Math.max(1, Math.min(1000, Number(e.target.value) || 1))); setPlan(null); }} /></label><button type="button" className="app-secondary-button" disabled={pending || disabled} onClick={() => void inspect()}>查看审阅用量</button></div>
      {plan && <div className="structure-review-plan"><p>{plan.model} · 本次 {plan.pages.length} / {plan.total_pages} 页 · 最多 {plan.max_calls} 次请求 · 每次最多输出 6000 token</p><p>{plan.image_scope}</p><p>{plan.notice}</p><div className="structure-review-row"><label>输入单价（元/百万 token）<input aria-label="审阅输入单价" type="number" min={0} step="0.1" value={inputPrice} disabled={pending} onChange={e => setInputPrice(e.target.value)} /></label><label>输出单价<input aria-label="审阅输出单价" type="number" min={0} step="0.1" value={outputPrice} disabled={pending} onChange={e => setOutputPrice(e.target.value)} /></label><label>估算预算（元）<input aria-label="审阅费用预算" type="number" min="0.01" step="0.1" value={maxCost} disabled={pending} onChange={e => setMaxCost(Math.max(0.01, Number(e.target.value) || 1))} /></label></div><p>按所填服务单价预留用量；预计超预算就停止派发。图片 token 为保守估算，最终以供应商账单为准。已完成页面复用，失败不自动重试。</p><button type="button" className="app-primary-button" disabled={!plan.ready || pending || disabled || !plan.pages.length || inputPrice === '' || outputPrice === ''} onClick={() => void start()}>{plan.ready ? '发送所选内容并开始审阅' : '请先配置识图模型'}</button></div>}
      {plan && !plan.has_original_pages && <div className="structure-review-row"><label>关联原始 PDF<input type="file" accept=".pdf,application/pdf" disabled={pending || disabled} onChange={e => setPdf(e.target.files?.[0] || null)} /></label><button type="button" className="app-secondary-button" disabled={!pdf || pending || disabled} onClick={() => void associatePdf()}>关联原页</button></div>}
    </>}{error && <p role="alert">{error}</p>}
  </section>;
}
