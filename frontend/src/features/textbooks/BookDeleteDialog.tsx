import { TexaClose } from '../../components/icons';

import Dialog from '../../components/ui/Dialog';
import { useBookDeletion } from './hooks/useBookDeletion';
import './textbookControls.css';

export default function BookDeleteDialog({ reference, onClose, onDeleted }: { reference: string; onClose: () => void; onDeleted: (name: string) => void }) {
  const state = useBookDeletion(reference, onDeleted);
  const locked = state.busy || state.stopping;
  return <Dialog open title="删除教材" onClose={() => { if (!locked) onClose(); }} className="textbook-delete-dialog">
    <header className="textbook-dialog-header"><div><h2>删除教材</h2></div><button type="button" className="app-icon-button" aria-label="关闭删除教材" disabled={locked} onClick={onClose}><TexaClose size={16} /></button></header>
    <div className="textbook-dialog-body">
      {!state.preview ? <p role="status">正在读取教材资料…</p> : <>
        <p className="textbook-delete-name">《{state.preview.display_name}》</p>
        {state.step === 1 ? <><p>同时删除：</p><ul><li>教材文件、OCR、图片和章节资料</li><li>当前及历史索引</li><li>概念、章节重点、教材内的练习和错题</li></ul><p className="textbook-muted">独立笔记、聊天记录和其他教材不会被删除。</p>
          {!!state.preview.active_jobs.length && <p role="status">继续后将停止该教材的运行任务。</p>}
        </> : <label className="textbook-delete-field">输入完整教材名以确认删除<input autoFocus className="app-field" value={state.name} onChange={e => state.setName(e.target.value)} placeholder={state.preview.display_name} disabled={state.busy} autoComplete="off" /></label>}
      </>}
      {state.stopping && <p role="status">正在停止任务…</p>}
      {state.error && <p role="alert" className="textbook-error">{state.error}</p>}
    </div>
    <footer className="textbook-dialog-footer"><button type="button" className="app-secondary-button" disabled={locked} onClick={onClose}>取消</button>{state.step === 1 ? <button type="button" className="app-primary-button" disabled={!state.preview || locked} onClick={() => void state.next()}>{state.stopping ? '正在停止任务…' : '继续确认'}</button> : <button type="button" className="app-secondary-button textbook-delete-confirm" disabled={state.busy || state.name !== state.preview?.display_name} onClick={() => void state.remove()}>{state.busy ? '正在删除…' : '永久删除教材'}</button>}</footer>
  </Dialog>;
}
