import type { CandidateSourceBlock, ExerciseCandidate } from '../../../types';
import { useState } from 'react';
import Dialog from '../../../components/ui/Dialog';
import { useAuthenticatedBlobUrl } from '../../../hooks/useAuthenticatedBlobUrl';

type Part = 'stem' | 'options' | 'subquestions' | 'figures_tables' | 'original_solution';
type Observation = { page: number; parts: Partial<Record<Part, string>> };
const labels: Record<Part, string> = { stem: '题干', options: '选项', subquestions: '子问', figures_tables: '图表', original_solution: '原书答案与解析' };
const states: Record<string, string> = { present: '原页已标出', missing: '原页未提供或仍缺失', unknown: '待对照原页', not_applicable: '原页未见此项' };

function OriginalPage({ sourceId, bookName, page }: { sourceId: string; bookName: string; page: number }) {
  const [retry, setRetry] = useState(0);
  const [zoom, setZoom] = useState(false);
  const query = new URLSearchParams({ kind: 'file', reference: sourceId, book_name: bookName, page: String(page) });
  const { url, loading, error } = useAuthenticatedBlobUrl(`/structure-reviews/source-page?${query}`, 'binary', retry);
  return <>
    {loading && <p role="status">正在读取原页…</p>}
    {error && <p role="alert">原页暂不可读：{error}。可在 AI 校对中关联对应原始 PDF。<button className="app-secondary-button" onClick={() => setRetry(v => v+1)}>重试读取原页</button></p>}
    {url && <><button className="app-secondary-button" aria-pressed={zoom} onClick={() => setZoom(!zoom)}>{zoom ? '适合窗口' : '放大原页'}</button><div className="exercise-original-page" tabIndex={0} role="region" aria-label="原页图像，可滚动查看"><img className={zoom ? 'is-zoomed' : ''} src={url} alt={`原始 PDF 物理页 ${page}`} /></div></>}
  </>;
}

export function CandidateCompleteness({ candidate, blocks, bookName }: { candidate: ExerciseCandidate; blocks: CandidateSourceBlock[]; bookName: string }) {
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const observations = candidate.projection?.method === 'user_edited' ? [] : blocks.flatMap(b => {
    const value: unknown = b.attributes.exercise_visual_inventory;
    return Array.isArray(value) ? value as Observation[] : [];
  });
  const pages = [...new Set(blocks.map(b => b.page_start).filter((p): p is number => p != null))].sort((a,b) => a-b);
  const parts = candidate.projection?.parts;
  const hasSource = (part: 'question' | 'answer' | 'explanation') => Boolean(parts?.[part].length);
  const figureCount = blocks.filter(b => b.block_type === 'figure' || b.block_type === 'table').length;
  const describe = (part: Part) => {
    const observed = [...new Set(observations.map(o => o.parts[part] || 'unknown'))];
    if (observed.length) return observed.map(value => states[value] || states.unknown).join('；');
    if (part === 'stem') return candidate.question_text.trim() && hasSource('question') ? '已有来源文字' : '待补全或核对边界';
    if (part === 'original_solution') return candidate.answer || candidate.explanation || hasSource('answer') || hasSource('explanation') ? '已保留原文' : '未提供';
    if (part === 'figures_tables') return figureCount ? `已关联 ${figureCount} 项，归属待核对` : '未关联，需对照原页';
    return '待对照原页';
  };
  const pageOnly = blocks.some(b => {
    const source: unknown = b.attributes.visual_source;
    return source != null && typeof source === 'object' && 'location' in source && source.location === 'page';
  });
  return <><details className="exercise-source-comparison exercise-completeness">
    <summary>题目组成与来源</summary>
    <dl className="exercise-source-values">{(Object.keys(labels) as Part[]).map(part => <div key={part}><dt>{labels[part]}</dt><dd>{describe(part)}</dd></div>)}
      <div><dt>来源定位</dt><dd>{pages.length ? `物理页 ${pages.join('、')}${pageOnly ? '，补录区域待定位' : ''}` : '未提供物理页定位'}</dd></div>
    </dl>
    <div className="exercise-row">{candidate.projection?.source_id && pages.map(page => <button className="app-ghost-button" key={page} onClick={() => setSelectedPage(page)}>对照物理页 {page}</button>)}</div>
    <p className="control-help">以上记录内容是否保留；完整性与数值、公式仍需对照原图核对。</p>
  </details><Dialog open={selectedPage != null} title={`物理页 ${selectedPage} · 原页对照`} onClose={() => setSelectedPage(null)} dismissOnBackdrop className="exercise-original-page-dialog">
    <h2>物理页 {selectedPage} · 原页对照</h2>
    {selectedPage != null && candidate.projection?.source_id && <OriginalPage key={selectedPage} sourceId={candidate.projection.source_id} bookName={bookName} page={selectedPage} />}
    <footer><button className="app-secondary-button" onClick={() => setSelectedPage(null)}>关闭原页对照</button></footer>
  </Dialog></>;
}
