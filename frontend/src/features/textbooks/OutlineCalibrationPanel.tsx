import { useState } from 'react';
import { X } from 'lucide-react';
import { useOutlineCalibration, type OutlineCandidate } from './hooks/useOutlineCalibration';
import './outlineCalibration.css';

export default function OutlineCalibrationPanel({ bookName, onClose }: { bookName: string; onClose: () => void }) {
  const state = useOutlineCalibration(bookName);
  const [chapter, setChapter] = useState('');
  const [query, setQuery] = useState('');
  const data = state.proposal || state.source;
  const chapterNames = [...new Set(state.source?.candidates.map(c => c.chapter) || [])];
  const selectedChapter = chapter || state.source?.chapters[0]?.title || chapterNames[0] || '';
  const candidates = state.source?.candidates.filter(c => query ? c.text.toLowerCase().includes(query.toLowerCase()) : c.chapter === selectedChapter) || [];
  const choose = (row: OutlineCandidate, value: string, role?: string) => {
    const others = state.examples.filter(e => e.block_id !== row.block_id);
    state.changeExamples(value === '' ? others : [...others, { block_id: row.block_id, level: Number(value), role: role || 'section' }]);
  };
  return <section className="outline-calibration" aria-label={`${bookName}目录校准`}>
    <header className="outline-calibration-header">
      <div><h3 className="type-section-title">校准目录</h3><p className="type-caption text-text-secondary">选一个有代表性的章节，指定少量标题。系统会将同类编号或样式应用到全书。</p></div>
      <button type="button" className="app-icon-button" aria-label="关闭目录校准" onClick={onClose}><X className="h-4 w-4" /></button>
    </header>
    {state.loading && <p role="status">正在读取教材结构…</p>}
    {state.error && <p role="alert" className="type-body">{state.error}</p>}
    {data && <>
      <div className="outline-calibration-tools">
        <label>示例章节<select className="app-field" aria-label="示例章节" value={selectedChapter} disabled={state.busy} onChange={e => { setChapter(e.target.value); setQuery(''); }}>{chapterNames.map(name => <option key={name}>{name}</option>)}</select></label>
        <label>查找原文<input className="app-field" placeholder="标题缺失时也可搜索正文" value={query} disabled={state.busy} onChange={e => setQuery(e.target.value)} /></label>
        <label>目录深度<select className="app-field" aria-label="目录深度" value={state.maxDepth} disabled={state.busy} onChange={e => state.changeDepth(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n} 级</option>)}</select></label>
      </div>
      <div className="outline-calibration-columns">
        <div><h4 className="type-control font-semibold">1. 指定示例</h4><p className="type-caption text-text-secondary">降为正文只移出目录，文字和题目仍然保留。</p>
          <div className="outline-calibration-list" aria-label="标题示例">
            {!candidates.length && <p className="type-caption">未找到对应文字，可换个关键词或章节。</p>}
            {candidates.map(row => {
              const example = state.examples.find(e => e.block_id === row.block_id);
              return <div key={row.block_id} className="outline-calibration-source">
                <div><p className="type-body">{row.text}</p><span className="type-caption text-text-secondary">物理页 {row.page || '未知'} · {row.level ? `${row.level} 级标题` : '正文'}</span></div>
                <div className="outline-calibration-choices">
                  <select aria-label={`${row.text}的层级`} className="app-field" value={example?.level ?? ''} disabled={state.busy} onChange={e => choose(row, e.target.value, example?.role)}><option value="">自动</option><option value="0">正文</option>{[1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n} 级标题</option>)}</select>
                  {(example?.level ?? row.level) > 0 && <select aria-label={`${row.text}的用途`} className="app-field" value={example?.role || row.role} disabled={state.busy} onChange={e => choose(row, String(example?.level ?? row.level), e.target.value)}><option value="section">普通章节</option><option value="exercise">习题区</option></select>}
                </div>
              </div>;
            })}
          </div>
        </div>
        <div><h4 className="type-control font-semibold">2. 全书预览</h4><p className="type-caption text-text-secondary">{state.proposal ? '已按示例重新整理，请检查其他章节后应用。' : '整理结果。修改示例后点击预览全书。'}</p>
          <div className="outline-calibration-list" aria-label="全书目录预览">
            {data.chapters.map((item, index) => <div key={`${item.title}:${index}`} className="outline-calibration-chapter">
              <p className="type-control font-semibold">{item.title}<span className="type-caption text-text-secondary"> · 第 {item.page_number} 页</span></p>
              {item.subsections.map(section => <p key={section.heading_block_id} className="type-body" style={{ paddingLeft: `${Math.min(section.level - 1, 5) * 12}px` }}>{section.title}<span className="type-caption text-text-secondary"> · {section.page}</span></p>)}
            </div>)}
          </div>
          {data.recovery.toc.some(t => (t.accepted || t.explicit) && t.entries > t.matched) && <p className="type-caption text-text-secondary">部分目录条目未定位到正文，已保留原文，可在左侧补充示例。</p>}
        </div>
      </div>
      <footer className="outline-calibration-footer">
        <p className="type-caption text-text-secondary" role="status">{state.job?.message || `已指定 ${state.examples.length} 个示例。应用后同步检索和习题范围，无需重新识别文字。`}</p>
        <div><button type="button" className="app-secondary-button" disabled={state.busy} onClick={() => void state.preview()}>预览全书</button><button type="button" className="app-primary-button" disabled={state.busy || !state.proposal} onClick={() => void state.apply()}>{state.busy && state.job ? '正在应用…' : '应用目录'}</button></div>
      </footer>
    </>}
  </section>;
}
