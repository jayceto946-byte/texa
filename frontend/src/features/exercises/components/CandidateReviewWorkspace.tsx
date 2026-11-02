import { StructureReviewControl } from '../../../components/StructureReviewControl';
import { get } from '../../../api/client';
import type { CandidateSourceRegistry } from '../../../types';
import Selector from '../../../components/ui/Selector';
import { useEffect, useRef, useState } from 'react';
import { ReadingMarkdown as SimpleMarkdown } from '../../reading/ReadingMarkdown';
import { HelpHint } from './HelpHint';
import type { ExerciseCandidate } from '../../../types';
import type { useExerciseImportCandidates } from '../hooks/useExerciseImportCandidates';
import { contentIssues, issueLabel, type Decisions } from '../hooks/candidateContract';
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
  const busy = parentBusy;
  const [currentId, setCurrentId] = useState('');
  const [pendingResult, setPendingResult] = useState<{ candidates: ExerciseCandidate[]; extract: CandidateSourceRegistry } | null>(null);
  const [adoptOpen, setAdoptOpen] = useState(false);
  const latestCandidates = useRef(s.candidates);
  useEffect(() => { latestCandidates.current = s.candidates; }, [s.candidates]);
  const dispatchedContent = useRef('');
  const editorOpen = useRef(s.editingCandidateId);
  useEffect(() => { editorOpen.current = s.editingCandidateId; }, [s.editingCandidateId]);
  const reviewSource = s.sourceRegistry?.review_reference || s.candidates[0]?.projection?.source_id;
  const latestSource = useRef(reviewSource);
  useEffect(() => { latestSource.current = reviewSource; }, [reviewSource]);
  const current = s.filteredCandidates.find(c => c.id === currentId) || s.filteredCandidates[0];
  useEffect(() => { if (s.editingCandidateId && s.filteredCandidates.some(c => c.id === s.editingCandidateId)) setCurrentId(s.editingCandidateId); }, [s.editingCandidateId, s.filteredCandidates]);
  const scrolls = useRef(new Map<string, number>());
  const readingPane = useRef<HTMLDivElement>(null);
  const select = (id: string) => { if (current && readingPane.current) scrolls.current.set(current.id, readingPane.current.scrollTop); setCurrentId(id); s.setEditingCandidateId(''); setReviewIssuesOpen(false); };
  const edit = current && s.editingCandidateId === current.id;
  const field = (label: string, key: 'question_text' | 'answer' | 'explanation', value: string) => <section className="exercise-edit-section" key={key}><h2>{label}</h2><RenderedMathEditor label={label} value={value} disabled={busy} onChange={text => s.updateCandidate(current.id, { [key]: text, ...(key === 'question_text' ? { duplicate_of: '' } : {}) })} /></section>;
  const signals = current ? contentIssues(current) : [];
  const sourceIds = new Set(current?.projection ? Object.values(current.projection.parts).flat().map(span => span.block_id) : []);
  const blocks = s.sourceRegistry?.source_blocks.filter(b => sourceIds.has(b.block_id)).sort((a,b) => a.order - b.order) || [];
  const splitAssets=blocks.filter(b=>b.block_type==='figure'||b.block_type==='table');
  const missingPages=s.sourceRegistry?.source_coverage?.filter(p=>p.status==='missing'||p.status==='unreadable') || [];
  const assignSplitAsset=(bid: string,owner: 'left'|'right'|'both')=>{
    const members=current?.projection?.dependencies.find(d=>d.kind==='figure'&&d.block_ids.includes(bid))?.block_ids || [bid];
    setSplitAssignment(a=>({...a,blocks:{...a.blocks,...Object.fromEntries(members.map(id=>[id,owner]))}}));
  };
  const applyResult = (result: { candidates: ExerciseCandidate[]; extract: CandidateSourceRegistry }) => { s.replaceCandidates(result.candidates, result.extract); setPendingResult(null); setReviewIssuesOpen(false); setAdoptOpen(false); onReviewed?.(result.candidates.length); };
  return <section className="exercise-candidate-review">
    <header className="exercise-review-toolbar">
      <div className="exercise-review-title"><h2>校对题目</h2><span title={source}>{source}</span></div>
      <div className="exercise-review-actions">
    {reviewSource && <StructureReviewControl compact candidateCount={s.candidates.length} onDispatch={() => { dispatchedContent.current = JSON.stringify(latestCandidates.current); setPendingResult(null); }} key={reviewSource} target={{ kind: 'file', reference: reviewSource, book_name: bookName }} disabled={parentBusy} onBusyChange={setReviewBusy} onComplete={async result => {
      if (!result?.source_id) return;
      const response = await get(`/exercises/file-sources/${result.source_id}/candidates?book_name=${encodeURIComponent(bookName)}&subject=${encodeURIComponent(s.candidates[0]?.subject || '')}`);
      if (latestSource.current !== reviewSource) return;
      if (!response.success) throw new Error(response.message || '无法读取审阅候选');
      const resultData = { candidates: response.data.candidates as ExerciseCandidate[], extract: response.data.extract as CandidateSourceRegistry };
      if (editorOpen.current || JSON.stringify(latestCandidates.current) !== dispatchedContent.current) setPendingResult(resultData);
      else applyResult(resultData);
    }} />}
        {pendingResult && <button className="app-secondary-button" onClick={() => setAdoptOpen(true)}>采用整理结果</button>}

      </div>
    </header>
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
            <div className="exercise-question"><SimpleMarkdown content={current.question_text} />{blocks.filter(b => b.block_type === 'figure' && current.projection?.parts.question.some(span => span.block_id === b.block_id)).map(b => current.projection?.source_id && typeof b.attributes.asset_id === 'string' ? <FileSourceImage key={b.block_id} sourceId={current.projection.source_id} assetId={b.attributes.asset_id} bookName={bookName} label={b.text} /> : null)}</div>
            {current.answer && <section className="exercise-candidate-answer"><h2>答案</h2><SimpleMarkdown content={current.answer} /></section>}

            {current.explanation && <section className="exercise-candidate-explanation"><h2>解析</h2><SimpleMarkdown content={current.explanation} /></section>}

          </>}
          {signals.filter(i => i.code !== 'edited_content').length > 0 && <div className="exercise-review-issues" ref={issuesPanel}><button className="app-secondary-button" aria-expanded={reviewIssuesOpen} onClick={() => setReviewIssuesOpen(!reviewIssuesOpen)}>核对 {signals.filter(i => i.code !== 'edited_content').length} 项</button>{reviewIssuesOpen && <div>
          {current.issues ? signals.filter(i => i.code !== 'edited_content').map(signal => <div className="exercise-warning exercise-content-issue" key={signal.key}>
            <p>{issueLabel(current, signal)}</p><button className="app-secondary-button" disabled={busy} onClick={() => { s.setEditingCandidateId(current.id); setReviewIssuesOpen(false); }}>编辑题目</button>
            {signal.code !== 'source_unavailable' && <label>本项处理<Selector ariaLabel={`处理：${issueLabel(current, signal)}`} value={s.reviewDecisions[current.id]?.[signal.key] || ''} onChange={value => {
              if (value) s.chooseResolution(current, signal.key, value as Decisions[string]);
            }} options={[{ value: "", label: "选择处理方式" }, ...(signal.code === 'missing_required_input' ? (current.projection?.dependencies.find(d => d.id === signal.dependency_id)?.kind === 'figure' ? [{ value: "not_applicable", label: "这道题不需要此图" }] : [{ value: "corrected", label: "已补全题目条件" }]) : [{ value: "corrected", label: "已修改" }, { value: "not_applicable", label: "检查过了，无需修改" }, { value: "source_checked", label: "已核对题目与答案" }])]} disabled={busy} compact/></label>}
          </div>) : current.validation_issues?.map(issue => <p className="exercise-warning" key={issue}>{issue}</p>)}
          </div>}</div>}
          {current.projection && <div className="exercise-structure-confirm"><button className="app-secondary-button" disabled={busy || Boolean(s.confirmingId) || signals.some(i => i.code !== 'edited_content' && !s.reviewDecisions[current.id]?.[i.key])} onClick={() => void s.confirmCandidate(current)}>{s.confirmingId === current.id ? '正在确认…' : '确认本题'}</button>{onSaveExample && current.review && (current.answer || current.explanation) && <button className="app-ghost-button" disabled={busy || !current.review || !current.answer && !current.explanation} onClick={() => onSaveExample(current)}>记住本题分离方式</button>}</div>}
        </article> : <p className="exercise-candidate-inner">{s.candidates.length ? '没有此类候选，整个批次及选择仍保留。' : '尚未识别题目。来源仍保留，可先用 AI 校对恢复原页正文。'}</p>}
      </div>

    </div>
    <footer className="exercise-commit"><span>已选 {s.selectedIds.size} 题{ s.sourceRegistry && s.selectedIds.size > s.submittableCandidates.length && <> · {s.selectedIds.size - s.submittableCandidates.length} 题待核对</>}</span><div><button className="app-ghost-button" disabled={busy || s.selectedIds.size < 2} onClick={s.mergeSelectedCandidates}>合并选中</button><button className="app-secondary-button" disabled={busy} onClick={onBack}>返回来源</button><button className="app-primary-button" disabled={busy || reviewBusy || Boolean(s.editingCandidateId) || Boolean(s.confirmingId) || !s.submittableCandidates.length} onClick={onSubmit}>{reviewBusy ? '正在整理…' : parentBusy ? '正在入库…' : s.sourceRegistry ? `确认入库${s.submittableCandidates.length}题` : '确认入库'}</button></div></footer>
    <Dialog open={adoptOpen} title="采用整理结果" onClose={() => setAdoptOpen(false)} dismissOnBackdrop className="structure-review-confirm"><h2>采用整理结果</h2><p>你已经手动修改过题目。要保留修改，还是换成整理后的内容？</p><footer><button className="app-secondary-button" onClick={() => setAdoptOpen(false)}>保留手动修改</button><button className="app-primary-button" onClick={() => pendingResult && applyResult(pendingResult)}>采用整理结果</button></footer></Dialog>
    <Dialog open={splitOpen} title="拆分题目" onClose={()=>setSplitOpen(false)} dismissOnBackdrop className="structure-review-confirm"><h2>拆分题目</h2><p>按题干中的第一处空行拆分。原解与附图需要明确归属；共享条件请分别保留在两题题干中。无法对齐来源时会保留当前内容，等待核对。</p>
      {current && (current.answer||current.explanation) && <label>原答案与解析<Selector ariaLabel="原答案与解析归属" value={splitAssignment.solution} onChange={value=>setSplitAssignment(a=>({...a,solution:value as SplitAssignment['solution']}))} options={[{value:'',label:'请选择归属'},{value:'left',label:'第一题'},{value:'right',label:'第二题'},{value:'separate',label:'分别分配（按原解空行）'}]}/></label>}
      {splitAssets.map(b=><label key={b.block_id}>{b.block_type==='figure'?'附图':'表格'} {b.text.slice(0,60)}<Selector ariaLabel={`来源归属 ${b.block_id}`} value={splitAssignment.blocks[b.block_id]||''} onChange={value=>assignSplitAsset(b.block_id,value as 'left'|'right'|'both')} options={[{value:'',label:'请选择归属'},{value:'left',label:'第一题'},{value:'right',label:'第二题'},{value:'both',label:'两题共用'}]}/></label>)}
      {splitError&&<p role="alert">{splitError}</p>}
      <footer><button className="app-secondary-button" onClick={()=>setSplitOpen(false)}>取消</button><button className="app-primary-button" disabled={!current || Boolean((current.answer||current.explanation)&&!splitAssignment.solution) || splitAssets.some(b=>!splitAssignment.blocks[b.block_id])} onClick={()=>{if(current){const result=s.splitCandidate(current,splitAssignment);if(result===true){setSplitOpen(false);setSplitError('');}else setSplitError(result);}}}>确认拆分</button></footer>
    </Dialog>
  </section>;
}
