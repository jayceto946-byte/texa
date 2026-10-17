import { useEffect, useRef, useState } from 'react';
import { ReadingMarkdown as SimpleMarkdown } from '../../reading/ReadingMarkdown';
import { HelpHint } from './HelpHint';
import type { ExerciseCandidate } from '../../../types';
import type { useExerciseImportCandidates } from '../hooks/useExerciseImportCandidates';

type CandidateState = ReturnType<typeof useExerciseImportCandidates>;
export function CandidateReviewWorkspace({ state: s, original, source, busy, message, onBack, onSubmit }: { state: CandidateState; original: string; source: string; busy: boolean; message: string; onBack: () => void; onSubmit: () => void }) {
  const [currentId, setCurrentId] = useState('');
  const [compare, setCompare] = useState(false);
  const [documentView, setDocumentView] = useState<'candidate' | 'original'>('candidate');
  const current = s.filteredCandidates.find(c => c.id === currentId) || s.filteredCandidates[0];
  useEffect(() => { if (s.editingCandidateId && s.filteredCandidates.some(c => c.id === s.editingCandidateId)) setCurrentId(s.editingCandidateId); }, [s.editingCandidateId, s.filteredCandidates]);
  const scrolls = useRef(new Map<string, number>());
  const document = useRef<HTMLDivElement>(null);
  const select = (id: string) => { if (current && document.current) scrolls.current.set(current.id, document.current.scrollTop); setCurrentId(id); };
  const edit = current && s.editingCandidateId === current.id;
  const field = (label: string, key: keyof ExerciseCandidate, value: string, multiline = false) => <label className="exercise-field" key={key}>{label}{multiline ? <textarea rows={key === 'question_text' ? 7 : 4} aria-label={`候选题${label}`} value={value} onChange={e => s.updateCandidate(current.id, { [key]: e.target.value, ...(key === 'question_text' ? { duplicate_of: '' } : {}) })} /> : <input value={value} onChange={e => s.updateCandidate(current.id, { [key]: e.target.value })} />}</label>;
  return <section className={`exercise-candidate-review ${compare ? 'is-comparing' : ''} show-${documentView}`}>
    <header className="exercise-review-heading">
      <div className="exercise-stages">1 选择来源 — <strong>2 校对候选</strong> — 3 确认入库</div>
      <div className="exercise-row">
        <h1>校对候选题</h1>{original && <button className="app-secondary-button" onClick={() => setCompare(!compare)}>{compare ? '返回候选索引' : '原文对照'}</button>}</div>
      <p>{source}</p>{message && <p role="status">{message}</p>}</header>
    {compare && <div className="exercise-compare-tabs">
      <button aria-pressed={documentView === 'candidate'} onClick={() => setDocumentView('candidate')}>候选题</button>
      <button aria-pressed={documentView === 'original'} onClick={() => setDocumentView('original')}>整段提取原文</button>
    </div>}
    <div className="exercise-review-body">
      <nav className="exercise-candidate-index" aria-label="候选题索引">
        <div className="exercise-candidate-filters">{([['all', '全部', s.candidates.length], ['issues', '需注意', s.importSummary.issues], ['duplicates', '重复', s.importSummary.duplicates]] as const).map(([value, label, count]) => <button key={value} aria-pressed={s.candidateFilter === value} onClick={() => s.setCandidateFilter(value)}>{label}<span>{count}</span>
        </button>)}</div>{s.filteredCandidates.map(c => <div key={c.id} className={`exercise-index-item ${current?.id === c.id ? 'is-current' : ''}`}>
          <input type="checkbox" aria-label={`选择候选题 ${c.id}`} checked={s.selectedIds.has(c.id)} onChange={() => s.toggleCandidate(c.id)} disabled={busy} />
          <button aria-current={current?.id === c.id ? 'true' : undefined} onClick={() => select(c.id)}>
            <strong>{String(s.candidates.indexOf(c) + 1).padStart(2, '0')} {c.question_text.replace(/\$[^$]*\$/g, '公式').slice(0, 64) || '题干待补全'}</strong>
            <small>{c.duplicate_of ? '重复 · 入库时跳过' : c.validation_issues?.length ? '需人工核对' : c.suggested_type || '待人工校对'}</small>
          </button>
        </div>)}<div className="exercise-index-tools">
          <button onClick={s.selectAllCandidates} disabled={busy}>全批次全选</button>
          <button onClick={s.clearCandidateSelection} disabled={busy}>清空选择</button>
        </div>
      </nav>
      <div className="exercise-candidate-document" key={current?.id || 'empty'} ref={element => { document.current = element; if (element && current) element.scrollTop = scrolls.current.get(current.id) || 0; }} onScroll={e => { if (current) scrolls.current.set(current.id, e.currentTarget.scrollTop); }}>
        {current ? <article className="exercise-candidate-inner">
          <div className="exercise-row">
            <span>{s.candidates.indexOf(current) + 1} / {s.candidates.length} {current.suggested_type}</span>
            <div>
              <button className="app-secondary-button" disabled={busy} onClick={() => s.setEditingCandidateId(edit ? '' : current.id)}>{edit ? '阅读预览' : '编辑'}</button>
              <button className="app-ghost-button" disabled={busy} onClick={() => { if (window.confirm('按第一空行拆分；原答案与解析将清空，请重新核对。')) s.splitCandidate(current); }}>拆分</button>
            </div>
          </div>
          {current.validation_issues?.map(issue => <p className="exercise-warning" key={issue}>{issue}</p>)}{current.duplicate_of && <p className="exercise-warning">重复于 {current.duplicate_of}，确认入库时跳过。</p>}{!current.question_text.trim() && <p className="exercise-warning">请补全题干或取消选择。</p>}
          {edit ? <fieldset disabled={busy} className="exercise-candidate-editor">{field('题干', 'question_text', current.question_text, true)}{field('标准答案', 'answer', current.answer, true)}{field('解析', 'explanation', current.explanation, true)}<div className="exercise-two">{field('题型', 'suggested_type', current.suggested_type)}<label className="exercise-field">难度（1–5）<input type="number" min="1" max="5" value={current.difficulty} onChange={e => s.updateCandidate(current.id, { difficulty: Math.max(1, Math.min(5, +e.target.value || 3)) })} />
          </label>
          </div>
            <label className="exercise-field">知识点标签<input value={current.tags.join(', ')} onChange={e => s.updateCandidate(current.id, { tags: e.target.value.split(',').map(x => x.trim()).filter(Boolean) })} />
            </label>
            <div className="exercise-two">{field('来源', 'source', current.source)}{field('章节', 'chapter', current.chapter)}</div>
          </fieldset> : <>
            <div className="exercise-question">
              <SimpleMarkdown content={current.question_text} />
            </div>
            <section className="exercise-candidate-answer">
              <h2>参考答案</h2>{current.answer ? <SimpleMarkdown content={current.answer} /> : <p>缺少参考答案，可留空入库。</p>}</section>
            <details className="exercise-properties">
              <summary>解析与题目属性</summary>
              <SimpleMarkdown content={current.explanation || '暂无解析'} />
              <p>{current.subject} · {current.chapter} · 难度 {current.difficulty}</p>
              <p>{current.source} · {current.tags.join('、')}</p>
              <p>解析置信度 {Math.round(current.confidence * 100)}%（不代表正确率）</p>
              <p>{current.reasons.join('；')}</p>
            </details>
          </>}
        </article> : <p className="exercise-candidate-inner">没有此类候选，整个批次及选择仍保留。</p>}
      </div>
      {compare && <div className="exercise-original">
        <h2>整段提取原文</h2>
        <pre>{original}</pre>
      </div>}
    </div>
    <footer className="exercise-commit">
      <span>已选 {s.selectedIds.size} / {s.candidates.length} 道<HelpHint label="候选选择">全选针对整个批次；选中不等于已校对。候选只在本页面内存中保留，刷新前请确认入库。</HelpHint>
      </span>
      <div>
        <button className="app-ghost-button" disabled={busy || s.selectedIds.size < 2} onClick={s.mergeSelectedCandidates}>合并选中</button>
        <button className="app-secondary-button" onClick={onBack}>返回来源</button>
        <button className="app-primary-button" disabled={busy || !s.selectedIds.size || s.candidates.some(c => s.selectedIds.has(c.id) && !c.question_text.trim())} onClick={onSubmit}>{busy ? '正在入库…' : '确认入库'}</button>
      </div>
    </footer>
  </section>;
}
