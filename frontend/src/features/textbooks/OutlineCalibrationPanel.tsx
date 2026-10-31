import { useEffect, useRef, useState } from 'react';
import { Plus, ArrowUpRight, RotateCcw } from 'lucide-react';
import { TexaClose } from '../../components/icons';
import Dialog from '../../components/ui/Dialog';
import Selector from '../../components/ui/Selector';
import { SegmentedControl } from '../../components/ui/SelectionControls';
import { outlineRequest, useOutlineCalibration, type OutlineEdit, type SourceBlock } from './hooks/useOutlineCalibration';
import './outlineCalibration.css';

export default function OutlineCalibrationPanel({ bookName, onClose, importJobId, onConfirmed }: {
  bookName: string; onClose: () => void; importJobId?: string; onConfirmed?: (jobId: string) => void;
}) {
  const state = useOutlineCalibration(bookName, importJobId, onConfirmed);
  const [selectedId, setSelectedId] = useState('');
  const [pageBlocks, setPageBlocks] = useState<SourceBlock[]>([]);
  const [pageError, setPageError] = useState('');
  const titleRef = useRef<HTMLInputElement>(null);
  const data = state.proposal || state.source;
  const sourceRows = (data?.candidates || []).filter(row => !(data?.edits || []).some(e => e.node_id === row.block_id && e.created) || state.edits.some(e => e.node_id === row.block_id));
  const rows = sourceRows.map(row => {
    const edit = state.edits.find(e => e.node_id === row.block_id);
    return { ...row, text: edit?.title ?? row.text, page: edit?.page ?? row.page, level: edit?.level ?? row.level };
  });
  for (const edit of state.edits) if (edit.created && !rows.some(row => row.block_id === edit.node_id)) {
    rows.push({ block_id: edit.node_id, text: edit.title, page: edit.page, level: edit.level, chapter: '', role: edit.role, family: '', visible: true });
  }
  const selected = rows.find(row => row.block_id === selectedId) || rows.find(row => row.level > 0);
  const selectedEdit = state.edits.find(e => e.node_id === selected?.block_id);
  const page = selected?.page ?? 1;
  const visibleRows = rows.filter(row => row.level > 0 && (row.level <= state.maxDepth || row.block_id === selected?.block_id))
    .sort((a, b) => (a.page || 1) - (b.page || 1));

  useEffect(() => {
    let alive = true;
    setPageError(''); setPageBlocks([]);
    outlineRequest<{ blocks: SourceBlock[] }>(`${state.root}/pages/${page}`).then(value => {
      if (alive) setPageBlocks(value.blocks);
    }).catch(error => { if (alive) { setPageBlocks([]); setPageError(error.message); } });
    return () => { alive = false; };
  }, [page, state.root]);

  const update = (values: Partial<OutlineEdit>) => {
    if (!selected) return;
    const edit: OutlineEdit = { node_id: selected.block_id, title: selected.text, level: selected.level,
      page, role: selected.role, anchor_block_id: selected.anchor_block_id || selected.block_id, ...selectedEdit, ...values };
    state.changeEdits([...state.edits.filter(e => e.node_id !== edit.node_id), edit]);
  };
  const addChapter = () => {
    const node_id = crypto.randomUUID();
    state.changeEdits([...state.edits, { node_id, created: true, title: '', page, level: 1, role: 'section' }]);
    setSelectedId(node_id);
    requestAnimationFrame(() => titleRef.current?.focus());
  };
  const remove = () => {
    if (!selected) return;
    if (selectedEdit?.created) state.changeEdits(state.edits.filter(e => e.node_id !== selected.block_id));
    else update({ level: 0 });
    setSelectedId('');
  };

  return <Dialog open title={importJobId ? '确认教材目录' : '校正教材目录'} onClose={onClose} className="outline-calibration-dialog">
    <section className="outline-calibration" aria-label={`${bookName}目录校正`}>
      <header className="outline-calibration-header"><div><h3>{importJobId ? '确认教材目录' : '校正教材目录'}</h3><p title={bookName}>{bookName}</p></div><button type="button" className="app-icon-button" aria-label="关闭目录校正" onClick={onClose}><TexaClose size={18} /></button></header>
      {state.loading && <p className="outline-message" role="status">正在读取目录…</p>}
      {state.error && <div className="outline-error" role="alert">{state.error}{!data && <button type="button" onClick={state.retry}>重试</button>}</div>}
      {data && <div className="outline-editor-workspace">
        <aside className="outline-sidebar" aria-label="教材目录">
          <div className="outline-sidebar-tools"><span>{rows.filter(row=>row.level===1).length} 章</span><button type="button" disabled={state.busy} onClick={addChapter}><Plus size={15} />新增一级标题</button></div>
          <SegmentedControl label="目录显示层级" value={String(state.maxDepth)} options={[{value:'1',label:'章'},{value:'2',label:'章和节'},{value:'6',label:'全部'}]} onChange={value => state.changeDepth(Number(value))} />
          <nav className="outline-title-list" aria-label="选择目录标题">
            {visibleRows.map(row => <button type="button" key={row.block_id} disabled={state.busy} aria-current={row.block_id === selected?.block_id ? 'true' : undefined} onClick={() => setSelectedId(row.block_id)} className={`${row.level === 1 ? 'is-chapter' : ''} ${row.block_id === selected?.block_id ? 'is-selected' : ''}`}>
              <span style={{paddingLeft: Math.min(row.level - 1, 3) * 12}}>{row.text || '新建章节'}</span><small>{row.page}</small>
            </button>)}
            {!visibleRows.length && <p className="outline-message">尚无目录，可先新增一级标题。</p>}
          </nav>
        </aside>
        <main className="outline-editor-detail">
          {selected ? <>
            <fieldset className="outline-edit-fields" disabled={state.busy}>
              <div className="outline-detail-heading"><h4>{selectedEdit?.created && !state.source?.candidates.some(row=>row.block_id===selected.block_id) ? '新增章节' : '编辑标题'}</h4><button type="button" onClick={remove}>移出目录</button></div>
              <label className="outline-field"><span>标题</span><input ref={titleRef} aria-label="目录标题" value={selected.text} maxLength={140} onChange={e => update({title:e.target.value})} placeholder="填写目录中缺失的章名" /></label>
              <div className="outline-field-pair"><label className="outline-field"><span>层级</span><Selector ariaLabel="标题层级" value={String(selected.level)} options={[1,2,3,4,5,6].map(n=>({value:String(n),label:n===1?'一级标题 · 章':n===2?'二级标题 · 节':`${n} 级标题`}))} onChange={value=>update({level:Number(value)})} /></label>
              <label className="outline-field"><span>起始物理页</span><input type="number" aria-label="起始物理页" min={1} max={data.page_count} value={page} onChange={e=>update({page:Number(e.target.value),anchor_block_id:''})} /></label></div>
              <div className="outline-role-control"><span>内容用途</span><SegmentedControl label="标题用途" value={selectedEdit?.role || selected.role} options={[{value:'section',label:'正文'},{value:'exercise',label:'习题区'}]} onChange={role=>update({role})} /></div>
            </fieldset>
            <section className="outline-source-page" aria-label="正文起点"><header><div><h4>正文起点</h4><p>选择标题前的原文位置，可在同一页内拆分章节。</p></div><span>第 {page} 页</span></header>
              {pageError && <p role="alert">{pageError}</p>}
              {!pageBlocks.length && !pageError && <p className="outline-message">这一页没有可定位的正文。</p>}
              <div role="radiogroup" aria-label="选择章节起点" onKeyDown={event=>{
                if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
                const buttons=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]'));
                const index=buttons.indexOf(document.activeElement as HTMLButtonElement);
                const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;
                event.preventDefault(); buttons[next]?.focus(); buttons[next]?.click();
              }}>{pageBlocks.map((block, index) => {
                const active = selectedEdit?.anchor_block_id ? selectedEdit.anchor_block_id === block.block_id : selectedEdit ? index === 0 : selected.block_id === block.block_id;
                return <button type="button" role="radio" aria-checked={active} key={block.block_id} disabled={state.busy} onClick={()=>update({anchor_block_id:block.block_id})} className={active?'is-anchor':''}><span className="outline-anchor-dot" /><span>{block.text}</span>{active && <ArrowUpRight size={15} />}</button>;
              })}</div>
            </section>
          </> : <div className="outline-message">从左侧选择标题，或新增缺失的一级标题。</div>}
        </main>
      </div>}
      <footer className="outline-calibration-footer"><div className="outline-footer-status" role="status">{state.job?.message || (importJobId ? '确认后建立索引并正式导入' : '保存后同步章节与检索范围')}</div><div><button type="button" className="app-icon-button" aria-label="恢复识别目录" title="恢复识别目录" disabled={state.busy || !data} onClick={()=>void state.reset()}><RotateCcw size={16}/></button><button type="button" className="app-secondary-button" disabled={state.busy || !data} onClick={()=>void state.preview()}>预览目录</button><button type="button" className="app-primary-button" disabled={state.busy || !data} onClick={()=>void state.apply()}>{state.busy?'正在处理…':importJobId?'确认目录并导入':'保存校正'}</button></div></footer>
    </section>
  </Dialog>;
}
