import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import './reading.css';
export type ReadingPane = 'question' | 'reference' | 'ai';
/** Geometry only. Domain state, jobs and writes remain in feature owners. */
export function QuestionReadingLayout({ title, meta, actions, question, reference, ai, aiLabel = 'AI 解题', questionLabel = '题目与来源', pane, onPaneChange, footer }: { title: string; meta: ReactNode; actions: ReactNode; question: ReactNode; reference: ReactNode; ai: ReactNode; aiLabel?: string; questionLabel?: string; pane: ReadingPane; onPaneChange: (pane: ReadingPane) => void; footer?: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [wide, setWide] = useState(false);
  useLayoutEffect(() => { const el = root.current; if (!el) return; const observer = new ResizeObserver(([entry]) => setWide(entry.contentRect.width >= 992)); observer.observe(el); return () => observer.disconnect(); }, []);
  const [opened, setOpened] = useState(pane !== 'question');
  const questionScroll = useRef<HTMLDivElement>(null);
  const solutionScroll = useRef<HTMLDivElement>(null);
  const scrollPositions = useRef({ question: 0, reference: 0, ai: 0 });
  useLayoutEffect(() => {
    if (questionScroll.current && (!opened || wide || pane === 'question')) questionScroll.current.scrollTop = scrollPositions.current.question;
    if (solutionScroll.current && opened && (wide || pane !== 'question')) solutionScroll.current.scrollTop = scrollPositions.current[pane === 'ai' ? 'ai' : 'reference'];
  }, [pane, opened, wide]);
  // Opening is sticky while switching among narrow panes; closing is explicit.
  const change = (next: ReadingPane) => { if (next !== 'question') setOpened(true); onPaneChange(next); };
  const tabs = <>
    <button aria-pressed={pane === 'reference'} onClick={() => change('reference')}>参考答案</button>
    <button aria-pressed={pane === 'ai'} onClick={() => change('ai')}>{aiLabel}</button>
  </>;
  return <div ref={root} className={`question-reading ${wide ? 'is-wide' : 'is-narrow'} ${opened ? 'is-open' : 'is-focused'} pane-${pane}`}>
    <header className="question-reading-heading">
      <div>
        <div className="question-reading-meta">{meta}</div>
        <h1>{title}</h1>
      </div>
      <div className="question-reading-actions">{actions}<button className="app-secondary-button" onClick={() => { if (opened) { setOpened(false); onPaneChange('question'); } else { setOpened(true); onPaneChange('reference'); } }}>{opened ? '收起解答' : '参考答案'}</button>
        <button className="app-secondary-button" onClick={() => change('ai')}>{aiLabel}</button>
      </div>
    </header>
    {opened && !wide && <nav className="question-reading-tabs" aria-label="阅读区域">
      <button aria-pressed={pane === 'question'} onClick={() => change('question')}>{questionLabel}</button>{tabs}</nav>}
    <div className="question-reading-body">
      <div ref={questionScroll} onScroll={e => { if (e.currentTarget.getBoundingClientRect().height) scrollPositions.current.question = e.currentTarget.scrollTop; }} className="question-reading-question" hidden={opened && !wide && pane !== 'question'}>
        <div className="question-reading-inner">{question}</div>
      </div>
      <div ref={solutionScroll} onScroll={e => { if (e.currentTarget.getBoundingClientRect().height) scrollPositions.current[pane === 'ai' ? 'ai' : 'reference'] = e.currentTarget.scrollTop; }} className="question-reading-solution" hidden={!opened || (!wide && pane === 'question')}>
        {wide && <nav className="question-reading-tabs" aria-label="解答类型">{tabs}</nav>}
        <section className="question-reading-solution-document" hidden={pane !== 'reference' && !(wide && pane === 'question')}>{reference}</section>
        <section className="question-reading-solution-document" hidden={pane !== 'ai'}>{ai}</section>
      </div>
    </div>{footer && <footer className="question-reading-footer">{footer}</footer>}
  </div>;
}
