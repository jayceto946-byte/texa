import { TexaClose } from '../../components/icons';
import { useState } from 'react';

import Dialog from '../../components/ui/Dialog';
import { useOutlineCalibration, type OutlineCandidate } from './hooks/useOutlineCalibration';
import './outlineCalibration.css';

export default function OutlineCalibrationPanel({ bookName, onClose }: { bookName: string; onClose: () => void }) {
  const state = useOutlineCalibration(bookName);
  const [chapter, setChapter] = useState('');
  const data = state.proposal || state.source;
  const chapters = data?.chapters || [];
  const rows = data?.candidates.filter(row => (row.visible || state.examples.some(e => e.block_id === row.block_id)) && (!chapter || row.chapter === chapter)) || [];
  const toc = data?.recovery.toc.filter(item => item.accepted) || [];
  const matched = toc.reduce((n, item) => n + item.matched, 0);
  const entries = toc.reduce((n, item) => n + item.entries, 0);
  const choose = (row: OutlineCandidate, value: string, role = 'section') => {
    const others = state.examples.filter(e => e.block_id !== row.block_id);
    state.changeExamples(value === '' ? others : [...others, { block_id: row.block_id, level: Number(value), role }]);
  };
  return <Dialog open title="校准目录" onClose={onClose} className="outline-calibration-dialog"><section className="outline-calibration" aria-label={`${bookName}目录校准`}>
    <header className="outline-calibration-header"><div><h3>校准目录<span> · {bookName}</span></h3></div><button type="button" className="app-icon-button" aria-label="关闭目录校准" onClick={onClose}><TexaClose size={16} /></button></header>
    {state.loading && <p role="status">正在匹配教材目录…</p>}
    {state.error && <p role="alert" className="textbook-error">{state.error}</p>}
    {data && <>
      <div className="outline-calibration-tools"><label>章节<select className="app-field" aria-label="筛选目录章节" value={chapter} disabled={state.busy} onChange={e => setChapter(e.target.value)}><option value="">全书目录</option>{chapters.map(item => <option key={item.title}>{item.title}</option>)}</select></label><label>显示层级<select className="app-field" aria-label="目录深度" value={state.maxDepth} disabled={state.busy} onChange={e => state.changeDepth(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n === 1 ? '章' : n === 2 ? '章和节' : `${n} 级标题`}</option>)}</select></label></div>
      <div className="outline-directory" aria-label="全书目录预览">
        <div className="outline-directory-head" aria-hidden="true"><span>目录标题</span><span>物理页</span><span>层级</span><span>用途</span></div>
        <div className="outline-directory-scroll">
          {!rows.length && <p className="outline-directory-empty">未识别到目录标题。</p>}
          {rows.map(row => {
            const example = state.examples.find(e => e.block_id === row.block_id);
            return <div key={row.block_id} className={`outline-directory-row${row.level === 1 ? ' is-chapter' : ''}`}>
              <span className="outline-directory-title" style={{ paddingLeft: `${Math.max(0, row.level - 1) * 16}px` }}>{row.text}</span><span className="outline-directory-page">{row.page || '—'}</span>
              <select className="app-field" aria-label={`${row.text}的层级`} value={example?.level ?? ''} disabled={state.busy} onChange={e => choose(row, e.target.value, example?.role || row.role)}><option value="">自动 · {row.level} 级</option><option value="0">移出目录</option>{[1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n} 级标题</option>)}</select>
              <select className="app-field" aria-label={`${row.text}的用途`} value={example?.role || row.role} disabled={state.busy || example?.level === 0} onChange={e => choose(row, String(example?.level ?? row.level), e.target.value)}><option value="section">章节</option><option value="exercise">习题区</option></select>
            </div>;
          })}
        </div>
      </div>
      {entries > matched && <p className="outline-calibration-note">{entries - matched} 个标题未匹配</p>}
      <footer className="outline-calibration-footer"><p role="status">{state.job?.message || (state.examples.length ? `${state.examples.length} 处修改` : '')}</p><div><button type="button" className="app-secondary-button" disabled={state.busy} onClick={() => void state.preview()}>预览全书</button><button type="button" className="app-primary-button" disabled={state.busy || !state.proposal} onClick={() => void state.apply()}>{state.busy && state.job ? '正在应用…' : '应用目录'}</button></div></footer>
    </>}
  </section></Dialog>;
}
