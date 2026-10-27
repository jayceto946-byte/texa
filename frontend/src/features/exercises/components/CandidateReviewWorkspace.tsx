import { useEffect, useRef, useState } from 'react';
import { ReadingMarkdown as SimpleMarkdown } from '../../reading/ReadingMarkdown';
import { HelpHint } from './HelpHint';
import type { ExerciseCandidate } from '../../../types';
import type { useExerciseImportCandidates } from '../hooks/useExerciseImportCandidates';
import { contentIssues, issueLabel, type Decisions } from '../hooks/candidateContract';
import { SourceRoleAssignment } from './SourceRoleAssignment';
import { SourceStructure } from './SourceStructure';

type CandidateState = ReturnType<typeof useExerciseImportCandidates>;
const roles = { question: '题干', answer: '答案', explanation: '解析', context: '旁文 / 资源线索', unassigned: '待定来源' };
export function CandidateReviewWorkspace({ state: s, original, source, busy, message, onBack, onSubmit, onSaveExample }: { state: CandidateState; original: string; source: string; busy: boolean; message: string; onBack: () => void; onSubmit: () => void; onSaveExample?: (candidate: ExerciseCandidate) => void }) {
  const [currentId, setCurrentId] = useState('');
  const [compare, setCompare] = useState(false);
  const [sourceView, setSourceView] = useState('current');
  const [focused, setFocused] = useState<string[]>([]);
  const [documentView, setDocumentView] = useState<'candidate' | 'original'>('candidate');
  const current = s.filteredCandidates.find(c => c.id === currentId) || s.filteredCandidates[0];
  useEffect(() => { if (s.editingCandidateId && s.filteredCandidates.some(c => c.id === s.editingCandidateId)) setCurrentId(s.editingCandidateId); }, [s.editingCandidateId, s.filteredCandidates]);
  const scrolls = useRef(new Map<string, number>());
  const document = useRef<HTMLDivElement>(null);
  const originalPane = useRef<HTMLDivElement>(null);
  useEffect(() => { if (focused.length) Array.from(originalPane.current?.querySelectorAll<HTMLElement>('[data-source-block]') || []).find(el => focused.includes(el.dataset.sourceBlock || ''))?.scrollIntoView({ block: 'nearest' }); }, [focused, compare, currentId]);
  const select = (id: string) => { if (current && document.current) scrolls.current.set(current.id, document.current.scrollTop); setCurrentId(id); setFocused([]); };
  const edit = current && s.editingCandidateId === current.id;
  const field = (label: string, key: keyof ExerciseCandidate, value: string, multiline = false) => <label className="exercise-field" key={key}>{label}{multiline ? <textarea rows={key === 'question_text' ? 7 : 4} aria-label={`候选题${label}`} value={value} onChange={e => s.updateCandidate(current.id, { [key]: e.target.value, ...(key === 'question_text' ? { duplicate_of: '' } : {}) })} /> : <input value={value} onChange={e => s.updateCandidate(current.id, { [key]: e.target.value })} />}</label>;
  const signals = current ? contentIssues(current) : [];
  const sourceIds = new Set(current?.projection ? Object.values(current.projection.parts).flat().map(span => span.block_id) : []);
  const blocks = s.sourceRegistry?.source_blocks.filter(b => sourceIds.has(b.block_id)).sort((a,b) => a.order - b.order) || [];
  const locate = (ids: string[]) => { setFocused(ids); setSourceView('current'); setCompare(true); setDocumentView('original'); };
  return <section className={`exercise-candidate-review ${compare ? 'is-comparing' : ''} show-${compare ? documentView : 'candidate'}`}>
    <header className="exercise-review-heading">
      <div className="exercise-stages">1 选择来源 — <strong>2 校对候选</strong> — 3 确认入库</div>
      <div className="exercise-row"><h1>校对候选题</h1>{original && <button className="app-secondary-button" onClick={() => setCompare(!compare)}>{compare ? '返回候选索引' : '原文对照'}</button>}</div>
      <p>{source}</p>{message && <p role="status">{message}</p>}
    </header>
    {compare && <div className="exercise-compare-tabs"><button aria-pressed={documentView === 'candidate'} onClick={() => setDocumentView('candidate')}>候选题</button><button aria-pressed={documentView === 'original'} onClick={() => setDocumentView('original')}>原文对照</button></div>}
    <div className="exercise-review-body">
      <nav className="exercise-candidate-index" aria-label="候选题索引">
        <div className="exercise-candidate-filters">{([['all', '全部', s.candidates.length], ['issues', s.sourceRegistry ? '内容待核对' : '需注意', s.sourceRegistry ? s.importSummary.content : s.importSummary.issues], ...(s.sourceRegistry ? [['metadata', '题目属性', s.importSummary.metadata] as const] : []), ['duplicates', '重复', s.importSummary.duplicates]] as const).map(([value, label, count]) => <button key={value} aria-pressed={s.candidateFilter === value} onClick={() => s.setCandidateFilter(value)}>{label}<span>{count}</span></button>)}</div>
        {s.filteredCandidates.map(c => <div key={c.id} className={`exercise-index-item ${current?.id === c.id ? 'is-current' : ''}`}>
          <input type="checkbox" aria-label={`选择候选题 ${c.id}`} checked={s.selectedIds.has(c.id)} onChange={() => s.toggleCandidate(c.id)} disabled={busy} />
          <button aria-current={current?.id === c.id ? 'true' : undefined} onClick={() => select(c.id)}><strong>{c.projection?.structure?.catalog_number || String(s.candidates.indexOf(c) + 1).padStart(2, '0')} {c.question_text.replace(/\$[^$]*\$/g, '公式').slice(0, 64) || '题干待补全'}</strong><small>{c.duplicate_of ? '重复 · 入库时跳过' : contentIssues(c)[0] ? issueLabel(c, contentIssues(c)[0]) : c.suggested_type || '题目'}</small></button>
        </div>)}
        <div className="exercise-index-tools"><button onClick={s.selectAllCandidates} disabled={busy}>全批次全选</button><button onClick={s.clearCandidateSelection} disabled={busy}>清空选择</button></div>
      </nav>
      <div className="exercise-candidate-document" key={current?.id || 'empty'} ref={element => { document.current = element; if (element && current) element.scrollTop = scrolls.current.get(current.id) || 0; }} onScroll={e => { if (current) scrolls.current.set(current.id, e.currentTarget.scrollTop); }}>
        {current ? <article className="exercise-candidate-inner">
          <div className="exercise-row"><span>{s.candidates.indexOf(current) + 1} / {s.candidates.length} {current.suggested_type}</span><div><button className="app-secondary-button" disabled={busy} onClick={() => s.setEditingCandidateId(edit ? '' : current.id)}>{edit ? '阅读预览' : '编辑'}</button><button className="app-ghost-button" disabled={busy} onClick={() => { if (window.confirm('按第一空行拆分；源答案与解析保留在后一子题及原文中，两题需重新校对。')) s.splitCandidate(current); }}>拆分</button></div></div>
          <SourceStructure value={current.projection?.structure} />
          {current.projection?.method === 'block_boundary' && <p className="exercise-projection-note">已按来源标记分离题干与解答，请核对归属。</p>}
          {current.issues ? signals.filter(i => i.code !== 'edited_content').map(signal => <div className="exercise-warning exercise-content-issue" key={signal.key}>
            <p>{issueLabel(current, signal)}</p><button disabled={busy} onClick={() => locate(signal.block_ids)}>定位原文</button><button disabled={busy} onClick={() => { locate(signal.block_ids); s.setEditingCandidateId(current.id); setDocumentView('candidate'); }}>对照并编辑</button>
            {signal.code !== 'source_unavailable' && <label>本项处理<select aria-label={`处理 ${signal.key}`} disabled={busy} value={s.reviewDecisions[current.id]?.[signal.key] || ''} onChange={e => { if (e.target.value) s.chooseResolution(current, signal.key, e.target.value as Decisions[string]); }}>
              <option value="">选择具体处理</option>{signal.code === 'missing_required_input' ? current.projection?.dependencies.find(d => d.id === signal.dependency_id)?.kind === 'figure' ? <option value="not_applicable">此图非必需，已改为独立文字题</option> : <option value="corrected">必要条件已补入题干</option> : <><option value="corrected">已编辑修正此项</option><option value="not_applicable">对照原文后判定为误报</option><option value="source_checked">已对照并接受当前源结构</option></>}
            </select></label>}
          </div>) : current.validation_issues?.map(issue => <p className="exercise-warning" key={issue}>{issue}</p>)}
          {current.duplicate_of && <p className="exercise-projection-note">重复于 {current.duplicate_of}，确认入库时跳过。</p>}
          {!current.question_text.trim() && <p className="exercise-warning">请补全题干或取消选择。</p>}
          {edit ? <fieldset disabled={busy} className="exercise-candidate-editor">{field('题干', 'question_text', current.question_text, true)}{field('标准答案', 'answer', current.answer, true)}{field('解析', 'explanation', current.explanation, true)}<div className="exercise-two">{field('题型', 'suggested_type', current.suggested_type)}<label className="exercise-field">难度（1–5）<input type="number" min="1" max="5" value={current.difficulty} onChange={e => s.updateCandidate(current.id, { difficulty: Math.max(1, Math.min(5, +e.target.value || 3)) })} /></label></div><label className="exercise-field">知识点标签<input value={current.tags.join(', ')} onChange={e => s.updateCandidate(current.id, { tags: e.target.value.split(',').map(x => x.trim()).filter(Boolean) })} /></label><div className="exercise-two">{field('来源', 'source', current.source)}{field('章节', 'chapter', current.chapter)}</div></fieldset> : <>
            <div className="exercise-question"><SimpleMarkdown content={current.question_text} /></div>
            <section className="exercise-candidate-answer"><h2>参考答案</h2>{current.answer ? <SimpleMarkdown content={current.answer} /> : <p>{current.explanation ? '暂无独立参考答案，解题过程见下方。' : '暂无源答案，可留空入库。'}</p>}</section>
            {current.explanation && <section className="exercise-candidate-explanation"><h2>解析</h2><SimpleMarkdown content={current.explanation} /></section>}
            <details className="exercise-properties"><summary>题目属性</summary>{current.issues?.filter(i => i.category === 'metadata').map(i => <p key={i.key}>{issueLabel(current,i)}</p>)}<p>{current.subject} · {current.chapter} · 难度 {current.difficulty}</p><p>{current.source} · {current.tags.join('、')}</p><p>解析置信度 {Math.round(current.confidence * 100)}%（不代表正确率）</p><p>{current.reasons.join('；')}</p></details>
          </>}
          {current.projection && <div className="exercise-structure-confirm"><button className="app-secondary-button" disabled={busy || Boolean(s.confirmingId) || signals.some(i => i.code !== 'edited_content' && !s.reviewDecisions[current.id]?.[i.key])} onClick={() => void s.confirmCandidate(current)}>{s.confirmingId === current.id ? '正在确认…' : '确认本题结构'}</button><span>{current.review ? '已确认当前版本' : current.projection.method === 'user_edited' ? '编辑后需重新确认当前题干及必要输入' : '可自愿确认；批量采用只记录系统提案'}</span>{onSaveExample && <button className="app-ghost-button" disabled={busy || !current.review || !current.answer && !current.explanation} onClick={() => onSaveExample(current)}>记住本题分离方式</button>}</div>}
        </article> : <p className="exercise-candidate-inner">没有此类候选，整个批次及选择仍保留。</p>}
      </div>
      {compare && <div className="exercise-original" ref={originalPane}><div className="exercise-row"><h2>原文对照</h2>{s.sourceRegistry && <select aria-label="原文范围" value={sourceView} onChange={e => setSourceView(e.target.value)}><option value="current">本题完整来源</option><option value="batch">整批提取原文</option></select>}</div>
        {sourceView === 'current' && blocks.length ? blocks.map(b => <section data-source-block={b.block_id} tabIndex={0} className={`exercise-source-block ${focused.includes(b.block_id) ? 'is-focused' : ''}`} key={b.block_id}><p className="exercise-source-position">物理页 {b.page_start ?? '未知'} · {Object.entries(current.projection!.parts).filter(([, spans]) => spans.some(span => span.block_id === b.block_id)).map(([role]) => roles[role as keyof typeof roles]).join(' / ')} · {b.block_type}</p><SimpleMarkdown content={b.block_type === 'formula' && !b.text.trim().startsWith('$$') ? `$$\n${b.text}\n$$` : b.text || '（无文字的资源块）'} /><details><summary>块位置及原始文字</summary><p>{b.block_id} · 顺序 {b.order} · 源页索引 {b.attributes.source_page_idx ?? '未知'} / 块索引 {b.attributes.source_block_index ?? '未知'}</p><pre>{b.text}</pre></details><SourceRoleAssignment block={b} disabled={busy} onAssign={(offset, role) => s.assignSource(current, b.block_id, offset, role)} /></section>) : <pre>{original}</pre>}
      </div>}
    </div>
    <footer className="exercise-commit"><span>已选 {s.selectedIds.size} / {s.candidates.length} 道{ s.sourceRegistry && <> · 可入库 {s.submittableCandidates.length} 题，另 {s.selectedIds.size - s.submittableCandidates.length} 题待核对</>}<HelpHint label="候选选择">全选针对整个批次；选中不等于已校对。未解决者保留候选。候选只在本页面内存中保留。</HelpHint></span><div><button className="app-ghost-button" disabled={busy || s.selectedIds.size < 2} onClick={s.mergeSelectedCandidates}>合并选中</button><button className="app-secondary-button" disabled={busy} onClick={onBack}>返回来源</button><button className="app-primary-button" disabled={busy || Boolean(s.editingCandidateId) || Boolean(s.confirmingId) || !s.submittableCandidates.length} onClick={onSubmit}>{busy ? '正在入库…' : s.sourceRegistry ? `确认入库${s.submittableCandidates.length}题` : '确认入库'}</button></div></footer>
  </section>;
}
