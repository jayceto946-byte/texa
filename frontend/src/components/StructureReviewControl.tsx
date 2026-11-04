import { useEffect, useRef, useState } from 'react';
import { apiFetch, get, post } from '../api/client';
import Dialog from './ui/Dialog';
import './structureReview.css';

type Target = { kind: 'book' | 'import' | 'file'; reference: string; book_name: string };
type Report = { source_additions?: number; page_content_coverage?: { selected_pages: number[]; reviewed_pages: number[]; completeness_verified: boolean }; status?: string; calls?: number; new_calls?: number; reused_calls?: number; text_coverage?: { total_batches: number; completed_batches: number; processed_blocks: number; total_blocks: number; original_pages: boolean }; candidate_coverage?: { before: number; after: number; removed: number; unaccounted: number; changes?: Array<{ reason: string; count: number }> }; model?: string; metadata_updates?: number; text_corrections?: number; merged_questions?: number; retained_answer_blocks?: number; changed_headings?: number; outline_changed?: boolean; estimated_cost_cny?: number | null; unresolved?: Array<string | { reason?: string; stage?: string; block_id?: string; page?: number }>; usage_unknown?: boolean; needs_retry?: boolean; failure?: { reason: string }; failures?: Array<{ key: string; reason: string }> };
type Job = { id: string; status: string; message: string; progress: number; result?: { source_id?: string; adoption_required?: boolean; adoption_blocked?: boolean; report?: Report } };
type Plan = { model: string; model_label?: string; provider: string; ready: boolean; pages: number[]; source_characters: number; includes_answer_file: boolean; estimated_cost: { low: number; high: number } | null; max_cost_cny: number; image_scope: string; has_original_pages: boolean };

export function StructureReviewControl({ target, disabled, compact = false, candidateCount, onDispatch, onComplete, onBusyChange }: { target: Target; disabled?: boolean; compact?: boolean; candidateCount?: number; onDispatch?: () => void; onComplete: (result: Job['result']) => void | Promise<void>; onBusyChange?: (busy: boolean) => void }) {
  const key = `texa:structure-review:${target.kind}:${target.reference}`;
  const [jobId, setJobId] = useState(() => localStorage.getItem(key) || '');
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [budget, setBudget] = useState(3);
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
        if (!payload.success) throw new Error(payload.message || '校对任务不存在');
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
      if (!response.success) throw new Error(response.message || '无法读取校对范围与模型');
      setPlan(response.data as Plan);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setPlanning(false); }
  };
  const associatePdf = async (file: File) => {
    setPlanning(true); setError('');
    const form = new FormData();
    form.append('kind', target.kind); form.append('reference', target.reference); form.append('book_name', target.book_name); form.append('file', file);
    try {
      const response = await apiFetch('/structure-reviews/source-pdf', { method: 'POST', body: form });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.detail || '关联PDF失败');
      await prepare();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setPlanning(false); }
  };
  const start = async (purpose: 'outline' | 'exercises' | 'textbook') => {
    if (dispatchLock.current) return;
    dispatchLock.current = true;
    setConfirmOpen(false); setStarting(true); setError(''); setJob(null); setStopping(false); onDispatch?.();
    try {
      const payload = await post('/structure-reviews', { ...target, purpose, retry_failed: retrying, max_cost_cny: budget });
      if (!payload.success) throw new Error(payload.message || '无法启动AI校对');
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
    report.metadata_updates ? `调整 ${report.metadata_updates} 处题目信息` : '', report.text_corrections ? `校正 ${report.text_corrections} 处文字` : '', report.merged_questions ? `合并 ${report.merged_questions} 道重复题` : '',
    report.retained_answer_blocks ? `保留 ${report.retained_answer_blocks} 个解答片段` : ''].filter(Boolean).join('，') : '';
  const reassembled=report?.candidate_coverage?.changes?.filter(c=>c.reason==='reassembled_source').reduce((sum,c)=>sum+c.count,0) || 0;
  return <section className={`structure-review-control${compact ? ' is-compact' : ''}`} aria-label="AI校对">
    <div className="structure-review-row">
      <button type="button" className="app-secondary-button" title={summary || undefined} disabled={busy || disabled || planning} onClick={() => void prepare()}>{busy ? `校对中 ${job?.progress || 0}%` : retrying ? '重试校对' : 'AI校对'}</button>
      {!compact && <span role="status">{busy ? `${job?.message || '正在准备校对'}${job ? ` · ${job.progress}%` : ''}` : summary || job?.message || (target.kind === 'file' ? '修正OCR识别错误，清理无关内容，匹配原书答案。' : '校正目录、页码与OCR识别文字。')}</span>}
      {busy && jobId && <button type="button" className="app-secondary-button" disabled={stopping} onClick={() => void stop()}>{stopping ? '正在停止' : '停止'}</button>}
    </div>
    {!compact && retrying && !busy && <p className="structure-review-hint">同版本复用已完成结果；来源或校对规则更新后会重新处理。{report?.usage_unknown ? '上次部分请求结果未知，重试可能再次计费。' : ''}</p>}
    {report && <details className="structure-review-receipt"><summary>校对记录{report.estimated_cost_cny != null ? ` · ¥${report.estimated_cost_cny.toFixed(4)}` : ''}</summary><div className="structure-review-record"><p>{report.model} · {job?.status === 'completed' ? `模型报告 ${report.unresolved?.length || 0} 项未确定内容` : '本次未完成，已知用量已保留'}。{report.usage_unknown ? '费用包含未知请求的预留，' : ''}实际以服务商账单为准。</p>{compact && summary && <p>{summary}。</p>}{report.calls!=null && <p>本次新请求 {report.new_calls ?? '未记录'} 次，复用已完成请求 {report.reused_calls ?? '未记录'} 次；来源累计请求 {report.calls} 次。</p>}{report.text_coverage && <p>文字批次完成 {report.text_coverage.completed_batches}/{report.text_coverage.total_batches}，处理来源块 {report.text_coverage.processed_blocks}/{report.text_coverage.total_blocks}。{report.text_coverage.original_pages?'已提供原始 PDF 页面。':'未提供完整原始 PDF，只能依据 OCR 文字及可用裁片核对。'}批次完成不代表每道题内容正确。</p>}{report.page_content_coverage && <p>原页审阅 {report.page_content_coverage.reviewed_pages.length}/{report.page_content_coverage.selected_pages.length} 页，补录 {report.source_additions || 0} 个来源片段。页面清单是模型观察，不代表已证实无漏题；请逐题对照原页。</p>}{report.candidate_coverage && <p>来源候选 {report.candidate_coverage.before} → {report.candidate_coverage.after} 道；减少 {report.candidate_coverage.removed} 道，其中 {report.candidate_coverage.unaccounted} 道未交代去向。{reassembled>0?`其中 ${reassembled} 个旧候选为误拆片段，已重新归入完整题目。`:''}{report.candidate_coverage.unaccounted>0?'结果未自动采用。':''}</p>}{report.failure && <p>{report.failure.reason}</p>}{report.failures?.map(f => <p key={f.key}>{f.key}：{f.reason}</p>)}{report.unresolved?.map((item, i) => <p key={i}>{typeof item === 'string' ? item : [item.stage, item.page ? `物理页 ${item.page}` : null, item.block_id, item.reason].filter(Boolean).join(' · ')}</p>)}</div></details>}
    {error && !confirmOpen && <p role="alert" className="structure-review-error">{error}</p>}
    <Dialog open={confirmOpen} title="AI校对" onClose={() => setConfirmOpen(false)} dismissOnBackdrop className="structure-review-confirm">
      <h2>AI校对</h2>
      <p>{target.kind === 'file' ? '对照原始来源校正题干、公式、选项与子问，分离原书答案，检查跨页边界，并提取考试年份、出处和题型。AI 修正后仍可人工编辑和核对。' : '帮助修正OCR中的错字和公式，清理无关内容，并校正目录层级和章节页码。'}</p>
      {planning ? <p role="status">正在读取校对范围与模型…</p> : plan && <>
        <dl><div><dt>处理范围</dt><dd>{target.kind === 'file' ? `所选来源的完整页面、OCR 文字与邻页上下文${candidateCount != null ? `（现有 ${candidateCount} 道候选）` : ''}` : '本次导入的教材'}，{plan.pages.length} 页{plan.includes_answer_file ? '，含独立答案文件' : ''}</dd></div>
        <div><dt>图像依据</dt><dd>{plan.image_scope}</dd></div>
        <div><dt>使用模型</dt><dd>{plan.model_label || plan.model}</dd></div></dl>
        {target.kind === 'file' && !plan.has_original_pages && <label className="structure-review-pdf">关联原始PDF<input type="file" accept="application/pdf,.pdf" onChange={e => { const file = e.target.files?.[0]; if (file) void associatePdf(file); }} /></label>}
        <details><summary>调整费用上限</summary><label>估算累计费用上限（元）<input className="app-field" aria-label="累计费用上限（元）" type="number" min="0.01" max="1000" step="0.5" value={budget} onChange={e => setBudget(Number(e.target.value))} /></label>{!plan.estimated_cost && <p>暂无该模型单价，金额上限无法用于本地预算控制，费用以服务商账单为准。</p>}</details>
        <p>确认后将上述范围的文字和相关图片发送给该模型。按实际用量计费，费用以模型服务商账单为准。</p>
        <p>校对期间可继续编辑，也可随时停止；已发送的请求可能仍会计费。</p>
        {!plan.ready && <p role="alert">请先到设置中配置识图模型。</p>}
      </>}
      {error && <p role="alert">{error}</p>}
      <footer><button className="app-secondary-button" onClick={() => setConfirmOpen(false)}>取消</button><button className="app-primary-button" disabled={!plan?.ready || planning || starting || !Number.isFinite(budget) || budget <= 0 || budget > 1000} onClick={() => void start(purpose)}>开始校对</button></footer>
    </Dialog>
  </section>;
}
