import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import app from './Workspace.tsx?raw';
import message from './components/ChatMessage.tsx?raw';
import chatPage from './pages/ChatPage.tsx?raw';
import mistakesPage from './pages/MistakesPage.tsx?raw';
import reviewSessionPage from './pages/ReviewSessionPage.tsx?raw';
import figureViewer from './features/visual-learning/FigureRegionViewer.tsx?raw';
import modelSettings from './components/settings/ModelSettingsManager.tsx?raw';
import asyncState from './components/ui/AsyncState.tsx?raw';
import { EmptyState, PageState } from './components/ui/AsyncState';
import { SegmentedControl, Tabs } from './components/ui/SelectionControls';
import loading from '../../desktop/loading.html?raw';
const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8');

// These checks protect user-visible flows and semantic states. Control styling and
// exact copy are intentionally free to evolve with the shared design system.
describe('Texa product UI contract', () => {
  it('keeps textbook import inside the library route', () => {
    expect(app).toContain('<Route path="books"');
    expect(app).toContain('<Route path="books/import"');
  });

  it('keeps sources inspectable and distinguishes uncertain citations', () => {
    expect(message).toContain('SourceInspectorContent');
    expect(message).toContain("kind: 'source'");
    expect(message).toContain("citationProvenance.status !== 'model_aligned'");
  });

  it('keeps errors actionable with optional technical detail', () => {
    expect(asyncState).toContain('export function ActionableIssue');
    expect(asyncState).toContain('actions: React.ReactNode');
    expect(asyncState).toContain('<details');
    expect(figureViewer).toContain('继续只使用文字');
  });

  it('renders a page state with one visible status surface', () => {
    const html = renderToStaticMarkup(createElement(PageState, { kind: 'empty', title: '暂无内容' }));
    expect(html.match(/role="status"/g)).toHaveLength(1);
    expect(html).not.toContain('app-panel');
  });

  it('exposes shared selection and empty states with their intended semantics', () => {
    const options = [{ value: 'one', label: '第一个' }, { value: 'two', label: '第二个' }] as const;
    const onChange = () => undefined;
    const segmented = renderToStaticMarkup(createElement(SegmentedControl, { label: '视图', value: 'one', options, onChange }));
    const tabs = renderToStaticMarkup(createElement(Tabs, { label: '页面', value: 'two', options, onChange, panelId: 'content' }));
    const empty = renderToStaticMarkup(createElement(EmptyState, { title: '暂无内容', description: '请稍后重试' }));

    expect(segmented).toContain('role="radiogroup"');
    expect(segmented).toContain('aria-checked="true"');
    expect(tabs).toContain('role="tablist"');
    expect(tabs).toContain('aria-selected="true"');
    expect(tabs).toContain('aria-controls="content"');
    expect(empty).toContain('role="status"');
  });

  it('keeps review and interrupted learning tasks resumable', () => {
    expect(app).toContain('path="learning/review/:sessionId"');
    expect(reviewSessionPage).toContain('get(`/review/sessions/${encodeURIComponent(sessionId)}');
    expect(reviewSessionPage).toContain('/results${query}');
    expect(mistakesPage).toContain('现在重做');
    expect(chatPage).toContain('resumeFigureTaskStream');
    expect(chatPage).toContain('interruptFigureTask');
  });

  it('keeps the composer usable with keyboard and attachment controls', () => {
    expect(chatPage).toContain('ComposerOverflowMenu');
    expect(chatPage).toContain('aria-label="发送问题"');
    expect(chatPage).toContain('FigureRegionViewer');
    expect(figureViewer).toContain('onKeyDown');
  });

  it('keeps independent and shared vision options', () => {
    expect(modelSettings).toContain("value.multimodal_mode === 'native'");
    expect(modelSettings).toContain('vision');
    expect(modelSettings).toContain('reasoning');
  });

  it('preserves distinct startup repair failures', () => {
    for (const code of ['MODEL_MISSING', 'MODEL_CORRUPT_OR_INCOMPATIBLE', 'ORT_IMPORT_FAILURE', 'TOKENIZER_MISMATCH']) {
      expect(loading).toContain(code);
    }
    expect(loading).toContain('repairEmbedding');
  });

  it('keeps CSS custom property references defined in the shared stylesheet', () => {
    const declared = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map((match) => match[1]));
    const used = [...css.matchAll(/var\((--[\w-]+)/g)].map((match) => match[1]);
    expect(used.filter((name) => !declared.has(name))).toEqual([]);
  });
});
