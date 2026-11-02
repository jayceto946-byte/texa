import { StructureReviewControl } from '../../../components/StructureReviewControl';
import { get, post } from '../../../api/client';
import type { CandidateSourceRegistry } from '../../../types';
import Selector from '../../../components/ui/Selector';
import { useEffect, useRef, useState } from 'react';
import { ReadingMarkdown as SimpleMarkdown } from '../../reading/ReadingMarkdown';
import { HelpHint } from './HelpHint';
import type { ExerciseCandidate } from '../../../types';
import type { useExerciseImportCandidates } from '../hooks/useExerciseImportCandidates';
import { contentIssues, issueLabel } from '../hooks/candidateContract';
import Dialog from '../../../components/ui/Dialog';
import { RenderedMathEditor } from '../../reading/RenderedMathEditor';
import { FileSourceImage } from './FileSourceImage';
import { SourceStructure } from './SourceStructure';
import type { SplitAssignment } from '../hooks/sourceSplit';

type CandidateState = ReturnType<typeof useExerciseImportCandidates>;
export function CandidateReviewWorkspace({ state: s, source, busy: parentBusy, notice, onReviewed, onBack, onSubmit, onSaveExample, bookName = 'default' }: { bookName?: string; state: CandidateState; source: string; busy: boolean; notice?: string; onReviewed?: (count: number) => void; onBack: () => void; onSubmit: () => void; onSaveExample?: (candidate: ExerciseCandidate) => void }) {
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewIssuesOpen, setReviewIssuesOpen] = useState(false);
  const [splitOpen,setSplitOpen]=useState(false);
  const [splitError,setSplitError]=useState('');
  const [splitAssignment,setSplitAssignment]=useState<SplitAssignment>({solution:'',blocks:{}});
  const issuesPanel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!reviewIssuesOpen) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Element;
      if (!issuesPanel.current?.contains(target) && !target.closest('[role="listbox"], .exercise-structure-confirm')) setReviewIssuesOpen(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setReviewIssuesOpen(false); };
    window.document.addEventListener('pointerdown', outside, true);
    window.document.addEventListener('keydown', escape);
    return () => { window.document.removeEventListener('pointerdown', outside, true); window.document.removeEventListener('keydown', escape); };
  }, [reviewIssuesOpen]);
  const [recoveryBusy,setRecoveryBusy]=useState(false);
  const [recoveryNotice,setRecoveryNotice]=useState('');
  const [recoverableSource,setRecoverableSource]=useState('');
  const [adoptionNote,setAdoptionNote]=useState('');
  const busy = parentBusy || recoveryBusy;
  const [currentId, setCurrentId] = useState('');
  const [pendingResult, setPendingResult] = useState<{ candidates: ExerciseCandidate[]; extract: CandidateSourceRegistry } | null>(null);
  const [adoptOpen, setAdoptOpen] = useState(false);
  const latestCandidates = useRef(s.candidates);
  useEffect(() => { latestCandidates.current = s.candidates; }, [s.candidates]);
  const dispatchedContent = useRef('');
  const editorOpen = useRef(s.editingCandidateId);
  useEffect(() => { editorOpen.current = s.editingCandidateId; }, [s.editingCandidateId]);
  const currentSource = s.sourceRegistry?.source_id || s.candidates[0]?.projection?.source_id;
  const reviewSource = s.sourceRegistry?.review_reference || currentSource;
  const latestSource = useRef(reviewSource);
  useEffect(() => { latestSource.current = reviewSource; }, [reviewSource]);
  const current = s.filteredCandidates.find(c => c.id === currentId) || s.filteredCandidates[0];
  useEffect(() => { if (s.editingCandidateId && s.filteredCandidates.some(c => c.id === s.editingCandidateId)) setCurrentId(s.editingCandidateId); }, [s.editingCandidateId, s.filteredCandidates]);
  const scrolls = useRef(new Map<string, number>());
  const readingPane = useRef<HTMLDivElement>(null);
  const select = (id: string) => { if (current && readingPane.current) scrolls.current.set(current.id, readingPane.current.scrollTop); setCurrentId(id); s.setEditingCandidateId(''); setReviewIssuesOpen(false); };
  const edit = current && s.editingCandidateId === current.id;
  const field = (label: string, key: 'question_text' | 'answer' | 'explanation', value: string) => <section className="exercise-edit-section" key={key}><h2>{label}</h2><RenderedMathEditor label={label} value={value} disabled={busy} onChange={text => s.updateCandidate(current.id, { [key]: text, ...(key === 'question_text' ? { duplicate_of: '' } : {}) })} /></section>;
  const signals = current && !current.review ? contentIssues(current) : [];
  const sourceIds = new Set(current?.projection ? Object.values(current.projection.parts).flat().map(span => span.block_id) : []);
  const blocks = s.sourceRegistry?.source_blocks.filter(b => sourceIds.has(b.block_id)).sort((a,b) => a.order - b.order) || [];
  const splitAssets=blocks.filter(b=>b.block_type==='figure'||b.block_type==='table');
  const figures = blocks.filter(b => b.block_type === 'figure' && typeof b.attributes.asset_id === 'string');
  const excludedFigures = new Set(current?.projection?.excluded_figure_ids || []);
  const toggleFigure = (blockId: string) => {
    if (!current?.projection) return;
    const next = new Set(excludedFigures);
    if (next.has(blockId)) next.delete(blockId); else next.add(blockId);
    s.updateCandidate(current.id, { projection: { ...current.projection, excluded_figure_ids: [...next] } });
  };
  const missingPages=s.sourceRegistry?.source_coverage?.filter(p=>p.status==='missing'||p.status==='unreadable') || [];
  const assignSplitAsset=(bid: string,owner: 'left'|'right'|'both')=>{
    const members=current?.projection?.dependencies.find(d=>d.kind==='figure'&&d.block_ids.includes(bid))?.block_ids || [bid];
    setSplitAssignment(a=>({...a,blocks:{...a.blocks,...Object.fromEntries(members.map(id=>[id,owner]))}}));
  };
  const applyResult = (result: { candidates: ExerciseCandidate[]; extract: CandidateSourceRegistry }) => { s.replaceCandidates(result.candidates, result.extract); setPendingResult(null); setReviewIssuesOpen(false); setAdoptOpen(false); setRecoveryNotice(''); setRecoverableSource(''); onReviewed?.(result.candidates.length); };
  const rebuild = async (restore: boolean) => {
    const sourceId=restore?reviewSource:recoverableSource || currentSource;
    if(!sourceId)return;
    setRecoveryBusy(true);setRecoveryNotice('');
    try {
      const response=await post(`/exercises/file-sources/${sourceId}/rebuild?book_name=${encodeURIComponent(bookName)}&subject=${encodeURIComponent(s.candidates[0]?.subject || '')}`,{});
      if(!response.success)throw new Error(response.message || '无法恢复候选');
      setPendingResult({candidates:response.data.candidates,extract:response.data.extract});
      setAdoptionNote(`${restore?'校对前来源':'已保存的校对来源'}已在本地重新生成 ${response.data.candidates.length} 道候选，未调用 AI。采用后将替换当前列表及手动修改；题目内容仍需核对。`);
      setAdoptOpen(true);
    } catch(cause){setRecoveryNotice(cause instanceof Error?cause.message:String(cause));}
    finally{setRecoveryBusy(false);}
  };
  return <section className="exercise-candidate-review">
    <header className="exercise-review-toolbar">
      <div className="exercise-review-title"><h2>校对题目</h2><span title={source}>{source}</span></div>
      <div className="exercise-review-actions">
    {reviewSource && <StructureReviewControl compact candidateCount={s.candidates.length} onDispatch={() => { dispatchedContent.current = JSON.stringify(latestCandidates.current); setPendingResult(null); }} key={reviewSource} target={{ kind: 'file', reference: reviewSource, book_name: bookName }} disabled={busy} onBusyChange={setReviewBusy} onComplete={async result => {
      if (!result?.source_id || latestSource.current !== reviewSource) return;
      if(result.adoption_blocked){
        setRecoverableSource(result.source_id);
        setRecoveryNotice('校对结果有来源题目未交代去向，已保留当前候选。请查看校对记录，可免费重新生成候选或恢复校对前来源。');
        return;
      }
      const response = await get(`/exercises/file-sources/${result.source_id}/candidates?book_name=${encodeURIComponent(bookName)}&subject=${encodeURIComponent(s.candidates[0]?.subject || '')}`);
      if (latestSource.current !== reviewSource) return;
      if (!response.success) throw new Error(response.message || '无法读取审阅候选');
      const resultData = { candidates: response.data.candidates as ExerciseCandidate[], extract: response.data.extract as CandidateSourceRegistry };
      if (result.adoption_required || resultData.candidates.length < latestCandidates.current.length || result.report?.status === 'partial' || result.report?.needs_retry || editorOpen.current || JSON.stringify(latestCandidates.current) !== dispatchedContent.current) {
        setPendingResult(resultData);
        setAdoptionNote(`校对结果有 ${resultData.candidates.length} 道候选，当前 ${latestCandidates.current.length} 道。${result.report?.status==='partial'?'本次校对尚有未完成项，请先查看校对记录。':''}采用将替换当前列表及手动修改。`);
        setRecoveryNotice('校对结果等待确认，当前候选已保留。');
      }
      else applyResult(resultData);
    }} />}
        {currentSource && <button className="app-secondary-button" disabled={busy || reviewBusy} title="使用已保存来源在本地重新分题，不调用 AI" onClick={()=>void rebuild(false)}>{recoveryBusy?'正在生成…':'重新生成候选'}</button>}
        {currentSource && reviewSource!==currentSource && <button className="app-secondary-button" disabled={busy || reviewBusy} onClick={()=>void rebuild(true)}>恢复校对前候选</button>}
        {pendingResult && <button className="app-secondary-button" onClick={() => setAdoptOpen(true)}>采用整理结果</button>}

      </div>
    </header>
    {recoveryNotice && <p role="status" className="exercise-candidate-notice">{recoveryNotice}</p>}
    {notice && <p role="alert" className="exercise-candidate-notice">{notice}</p>}
    {missingPages.length>0 && <p className="exercise-candidate-notice">物理页 {missingPages.slice(0,12).map(p=>p.page).join('、')}{missingPages.length>12?'等':''} 共 {missingPages.length} 页尚无可用正文。有原始 PDF 时可用 AI 校对恢复；缺少原页请补充对应 PDF。未识别不代表本页没有题目。</p>}
    <div className="exercise-review-body">
      <nav className="exercise-candidate-index" aria-label="候选题索引">
        <div className="exercise-candidate-filters">{([['all', '全部', s.candidates.length], ['issues', s.sourceRegistry ? '待核对' : '需注意', s.sourceRegistry ? s.importSummary.content : s.importSummary.issues], ['duplicates', '重复', s.importSummary.duplicates]] as const).map(([value, label, count]) => <button key={value} aria-pressed={s.candidateFilter === value} onClick={() => { s.setCandidateFilter(value); setReviewIssuesOpen(false); }}>{label}<span className="exercise-filter-count">{count}</span></button>)}</div>
        <div className="exercise-candidate-list">
        {s.filteredCandidates.map(c => <div key={c.id} className={`exercise-index-item ${current?.id === c.id ? 'is-current' : ''}`}>
          <input type="checkbox" aria-label={`选择候选题 ${c.id}`} checked={s.selectedIds.has(c.id)} onChange={() => s.toggleCandidate(c.id)} disabled={busy} />
          <button aria-current={current?.id === c.id ? 'true' : undefined} onClick={() => select(c.id)}><strong>{c.question_text.replace(/\$[^$]*\$/g, '公式').slice(0, 64) || '题干待补全'}</strong></button>{(c.duplicate_of || contentIssues(c).length > 0) && <HelpHint label="本题提示">{c.duplicate_of ? '重复题，入库时跳过。' : contentIssues(c).map(i => issueLabel(c, i)).join('；')}</HelpHint>}
        </div>)}
        <div className="exercise-index-tools"><button onClick={s.selectAllCandidates} disabled={busy}>全批次全选</button><button onClick={s.clearCandidateSelection} disabled={busy}>清空选择</button></div>
        </div>
      </nav>
      <div className="exercise-candidate-document" key={current?.id || 'empty'} ref={element => { readingPane.current = element; if (element && current) element.scrollTop = scrolls.current.get(current.id) || 0; }} onScroll={e => { if (current) scrolls.current.set(current.id, e.currentTarget.scrollTop); }}>
        {current ? <article className="exercise-candidate-inner">
          <div className="exercise-row exercise-candidate-toolbar"><span>{s.candidates.indexOf(current) + 1} / {s.candidates.length}</span><div><button className="app-secondary-button" disabled={busy} onClick={() => s.setEditingCandidateId(edit ? '' : current.id)}>{edit ? '完成编辑' : '编辑题目'}</button><button className="app-secondary-button" disabled={busy} onClick={() => { setSplitAssignment({solution:'',blocks:{}});setSplitError('');setSplitOpen(true); }}>拆分</button></div></div>

          <SourceStructure value={current.projection?.structure} />
          {blocks.some(b => b.attributes.original_ocr_text) && <details className="exercise-source-comparison"><summary>查看 AI 修正对照</summary>{blocks.filter(b => b.attributes.original_ocr_text).map(b => <section key={b.block_id}><p className="control-help">{b.page_start ? `物理页 ${b.page_start} · 原始识别` : '原始识别'}</p><SimpleMarkdown content={String(b.attributes.original_ocr_text)} /><p className="control-help">AI 校正后</p><SimpleMarkdown content={b.text} /></section>)}</details>}
          {!current.question_text.trim() && <p className="exercise-warning">请补全题干或取消选择。</p>}
          {edit ? <fieldset disabled={busy} className="exercise-candidate-editor">{field('题干', 'question_text', current.question_text)}{field('答案', 'answer', current.answer)}{field('解析', 'explanation', current.explanation)}</fieldset> : <>
            <div className="exercise-question"><SimpleMarkdown content={current.question_text} />{blocks.filter(b => b.block_type === 'figure' && !excludedFigures.has(b.block_id) && current.projection?.parts.question.some(span => span.block_id === b.block_id)).map(b => current.projection?.source_id && typeof b.attributes.asset_id === 'string' ? <FileSourceImage key={b.block_id} sourceId={current.projection.source_id} assetId={b.attributes.asset_id} bookName={bookName} label={b.text} /> : null)}</div>
            {current.answer && <section className="exercise-candidate-answer"><h2>答案</h2><SimpleMarkdown content={current.answer} /></section>}

            {current.explanation && <section className="exercise-candidate-explanation"><h2>解析</h2><SimpleMarkdown content={current.explanation} /></section>}

          </>}
          {figures.length > 0 && <section className="exercise-figure-manager">
            <h2>题目配图 <span>可移除误带入的笔记或图片</span></h2>
            {figures.map(b => <div className={`exercise-figure-item ${excludedFigures.has(b.block_id) ? 'is-removed' : ''}`} key={b.block_id}>
              {!excludedFigures.has(b.block_id) && edit && current.projection?.source_id && <FileSourceImage sourceId={current.projection.source_id} assetId={String(b.attributes.asset_id)} bookName={bookName} label={b.text || '题目配图'} />}
              <div><span>{b.text || '配图'}{b.page_start ? ` · 物理页 ${b.page_start}` : ''}{excludedFigures.has(b.block_id) ? ' · 已移除' : ''}</span><button className="app-secondary-button" disabled={busy} onClick={() => toggleFigure(b.block_id)}>{excludedFigures.has(b.block_id) ? '恢复图片' : '移除图片'}</button></div>
            </div>)}
          </section>}
          {signals.filter(i => i.code !== 'edited_content').length > 0 && <div className="exercise-review-issues" ref={issuesPanel}>
            <button className="app-ghost-button" aria-expanded={reviewIssuesOpen} onClick={() => setReviewIssuesOpen(!reviewIssuesOpen)}>待核对提示 {signals.filter(i => i.code !== 'edited_content').length} 项 · 可先导入</button>
            {reviewIssuesOpen && <ul>{[...new Set(signals.filter(i => i.code !== 'edited_content').map(signal => issueLabel(current, signal)))].map(label => <li key={label}>{label}</li>)}</ul>}
          </div>}
          {current.projection && <div className="exercise-structure-confirm"><span>{current.review ? '已标记核对' : '无需逐题确认，选中后即可批量导入'}</span><button className="app-ghost-button" disabled={busy || Boolean(s.confirmingId) || Boolean(current.review)} onClick={() => void s.confirmCandidate(current)}>{s.confirmingId === current.id ? '正在记录…' : '标记已核对'}</button>{onSaveExample && current.review && (current.answer || current.explanation) && <button className="app-ghost-button" disabled={busy} onClick={() => onSaveExample(current)}>记住本题分离方式</button>}</div>}
        </article> : <p className="exercise-candidate-inner">{s.candidates.length ? '没有此类候选，整个批次及选择仍保留。' : '尚未识别题目。来源仍保留，可先用 AI 校对恢复原页正文。'}</p>}
      </div>

    </div>
    <footer className="exercise-commit"><span>已选 {s.selectedIds.size} 题 · 可导入 {s.submittableCandidates.length} 题<small>待核对提示随题保留，可入库后继续整理</small></span><div><button className="app-ghost-button" disabled={busy || s.selectedIds.size < 2} onClick={s.mergeSelectedCandidates}>合并选中</button><button className="app-secondary-button" disabled={busy} onClick={onBack}>返回来源</button><button className="app-primary-button" disabled={busy || reviewBusy || Boolean(s.confirmingId) || !s.submittableCandidates.length} onClick={onSubmit}>{reviewBusy ? '正在整理…' : parentBusy ? '正在入库…' : `导入选中 ${s.submittableCandidates.length} 题`}</button></div></footer>
    <Dialog open={adoptOpen} title="采用整理结果" onClose={() => setAdoptOpen(false)} dismissOnBackdrop className="structure-review-confirm"><h2>采用整理结果</h2><p>{adoptionNote}</p><footer><button className="app-secondary-button" onClick={() => setAdoptOpen(false)}>保留当前候选</button><button className="app-primary-button" onClick={() => pendingResult && applyResult(pendingResult)}>采用整理结果</button></footer></Dialog>
    <Dialog open={splitOpen} title="拆分题目" onClose={()=>setSplitOpen(false)} dismissOnBackdrop className="structure-review-confirm"><h2>拆分题目</h2><p>按题干中的第一处空行拆分。原解与附图需要明确归属；共享条件请分别保留在两题题干中。无法对齐来源时会保留当前内容，等待核对。</p>
      {current && (current.answer||current.explanation) && <label>原答案与解析<Selector ariaLabel="原答案与解析归属" value={splitAssignment.solution} onChange={value=>setSplitAssignment(a=>({...a,solution:value as SplitAssignment['solution']}))} options={[{value:'',label:'请选择归属'},{value:'left',label:'第一题'},{value:'right',label:'第二题'},{value:'separate',label:'分别分配（按原解空行）'}]}/></label>}
      {splitAssets.map(b=><label key={b.block_id}>{b.block_type==='figure'?'附图':'表格'} {b.text.slice(0,60)}<Selector ariaLabel={`来源归属 ${b.block_id}`} value={splitAssignment.blocks[b.block_id]||''} onChange={value=>assignSplitAsset(b.block_id,value as 'left'|'right'|'both')} options={[{value:'',label:'请选择归属'},{value:'left',label:'第一题'},{value:'right',label:'第二题'},{value:'both',label:'两题共用'}]}/></label>)}
      {splitError&&<p role="alert">{splitError}</p>}
      <footer><button className="app-secondary-button" onClick={()=>setSplitOpen(false)}>取消</button><button className="app-primary-button" disabled={!current || Boolean((current.answer||current.explanation)&&!splitAssignment.solution) || splitAssets.some(b=>!splitAssignment.blocks[b.block_id])} onClick={()=>{if(current){const result=s.splitCandidate(current,splitAssignment);if(result===true){setSplitOpen(false);setSplitError('');}else setSplitError(result);}}}>确认拆分</button></footer>
    </Dialog>
  </section>;
}
