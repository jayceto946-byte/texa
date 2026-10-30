import { TexaClose } from '../../components/icons';
import { useState } from 'react';

import Dialog from '../../components/ui/Dialog';
import { useOptionalConceptJob } from './hooks/useOptionalConceptJob';
import './textbookControls.css';

const labels: Record<string, string> = { queued: '概念待提取', running: '概念抽取中', cancelling: '正在停止抽取', completed: '概念已提取', failed: '概念抽取失败', cancelled: '概念抽取已停止', interrupted: '概念抽取已中断' };
export default function ConceptExtractionStatus({ bookName, jobId = '' }: { bookName: string; jobId?: string }) {
  const state = useOptionalConceptJob(bookName, jobId);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const job = state.job;
  const running = !!job && ['queued', 'running', 'cancelling'].includes(job.status);
  const failed = !!job && ['failed', 'interrupted'].includes(job.status);
  return <section aria-label={`${bookName}概念抽取`} className="textbook-concept-status">
    <div className="textbook-concept-line">
      {!state.loaded ? <span role="status">读取概念状态…</span> : job && <span role="status">{labels[job.status] || job.status}{running ? ` · ${job.progress}%` : job.status === 'completed' ? ` · ${job.result?.concept_count || 0} 个` : ''}</span>}
      {running ? <button type="button" className="textbook-text-action" disabled={state.busy || job.status === 'cancelling'} onClick={() => void state.cancel()}>{job.status === 'cancelling' ? '等待确认…' : '停止'}</button> : state.loaded && <button type="button" className="textbook-text-action" disabled={state.busy || !!state.error} onClick={() => setConfirmOpen(true)}>{job ? '重新提取' : '提取概念'}</button>}
    </div>
    {job?.status === 'cancelling' && <p className="textbook-concept-detail">等待当前请求结束…</p>}
    {(failed || state.error) && <details className="textbook-concept-detail"><summary>查看原因</summary><p role="alert">{state.error || job?.error || job?.message}</p></details>}
    <Dialog open={confirmOpen} title="提取教材概念" onClose={() => setConfirmOpen(false)} className="textbook-delete-dialog">
      <header className="textbook-dialog-header"><h2>提取教材概念</h2><button type="button" className="app-icon-button" aria-label="关闭概念提取确认" onClick={() => setConfirmOpen(false)}><TexaClose size={16} /></button></header>
      <div className="textbook-dialog-body"><p>将教材片段发送到已配置的模型，可能产生费用。</p></div>
      <footer className="textbook-dialog-footer"><button type="button" className="app-secondary-button" onClick={() => setConfirmOpen(false)}>取消</button><button type="button" className="app-primary-button" onClick={() => { setConfirmOpen(false); void state.start(); }}>开始提取</button></footer>
    </Dialog>
  </section>;
}
