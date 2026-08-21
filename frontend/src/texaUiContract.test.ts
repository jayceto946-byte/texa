import { describe, expect, it } from 'vitest';
import app from './App.tsx?raw';
import message from './components/ChatMessage.tsx?raw';
import firstRun from './components/FirstRunGuide.tsx?raw';
import emptyWorkspace from './components/chat/LearningEmptyWorkspace.tsx?raw';
import execution from './components/chat/ExecutionTrace.tsx?raw';
import shell from './layouts/MainLayout.tsx?raw';
import rail from './components/AppRail.tsx?raw';
import learningContext from './components/LearningContextSidebar.tsx?raw';
import chatPage from './pages/ChatPage.tsx?raw';
import exercisesPage from './pages/ExercisesPage.tsx?raw';
import composerOverflow from './components/chat/ComposerOverflowMenu.tsx?raw';
import appearance from './components/settings/AppearanceSettings.tsx?raw';
import settings from './components/SystemHealth.tsx?raw';
import theme from './theme.ts?raw';
import desktopTitleBar from './components/DesktopTitleBar.tsx?raw';
import desktopMain from '../../desktop/main.cjs?raw';
import loading from '../../desktop/loading.html?raw';

describe('Texa product UI contract', () => {
  it('keeps Library as the object and import as a nested action', () => {
    expect(app).toContain('<Route path="books" element={<SettingsPage standaloneTab="subjects" />} />');
    expect(app).toContain('<Route path="books/import" element={<BooksPage />} />');
    expect(rail).toContain("label: '教材'");
    expect(rail).not.toContain("label: '教材导入'");
  });

  it('keeps sources and concepts in the contextual inspector', () => {
    expect(app).toContain('<InspectorProvider>');
    expect(shell).toContain('<ContextInspector />');
    expect(message).toContain('SourceInspectorContent');
    expect(message).toContain("kind: 'source'");
    expect(message).toContain("kind: 'concept'");
  });

  it('separates product navigation from learning context', () => {
    expect(shell).toContain('<AppRail />');
    expect(shell).toContain('<LearningContextSidebar');
    expect(rail).not.toContain('ScopeSelector');
    expect(rail).not.toContain('新会话');
    expect(learningContext).toContain('当前学习范围');
    expect(learningContext).toContain('历史记录');
    expect(learningContext).toContain('新会话');
    expect(learningContext).not.toContain("activeConversation?.title");
    expect(learningContext).toContain('sessionScopeLabel');
  });

  it('keeps visited routes and the learning context mounted without route loading copy', () => {
    expect(app).not.toContain('lazy(');
    expect(shell).toContain('<PersistentRouteOutlet />');
    expect(shell).toContain('setCachedOutlets(renderedOutlets)');
    expect(shell).toContain('className="persistent-route-panel"');
    expect(shell).toContain('hidden={!isLearningWorkspace || !contextOpen}');
    expect(shell).not.toContain('正在打开页面');
    expect(learningContext).toContain('conversationCacheKey');
    expect(learningContext).toContain('writeCache(cacheKey, rows)');
  });

  it('keeps the composer as one responsive surface with an internal overflow menu', () => {
    expect(chatPage).toContain('className="composer-surface"');
    expect(chatPage).toContain('className="composer-toolbar"');
    expect(chatPage).not.toMatch(/messages\.length\s*>\s*0[\s\S]{0,120}<ComposerOverflowMenu>/);
    expect(composerOverflow).toContain('className="composer-overflow-menu"');
    expect(composerOverflow).toContain('aria-label="更多"');
    expect(composerOverflow).toContain("event.key !== 'Escape'");
    expect(composerOverflow).toContain("document.addEventListener('pointerdown'");
    expect(chatPage).toContain('aria-label="发送问题"');
    expect(chatPage).not.toContain('chat-toolbar mx-auto');
  });

  it('uses a semantic, locally persisted appearance theme registry', () => {
    expect(settings).toContain("{ id: 'appearance', label: '外观' }");
    expect(settings).toContain('<AppearanceSettings />');
    expect(appearance).toContain('role="radiogroup"');
    expect(appearance).toContain('applyTexaTheme(nextThemeId)');
    expect(theme).toContain("id: 'mineral'");
    expect(theme).toContain("id: 'graphite'");
    expect(theme).toContain("id: 'clay'");
    expect(theme).toContain("id: 'notebook'");
    expect(theme).toContain("id: 'codex'");
    expect(theme).toContain("'--color-accent'");
  });

  it('renders a question as a lightweight query header with a separate attachment row', () => {
    expect(message).toContain('splitQuestionAttachment');
    expect(message).toContain('className="learning-query-attachment"');
    expect(message).toContain('附件：{questionContent.attachmentName}');
  });

  it('shares one desktop header geometry and keeps responsive custom window controls', () => {
    expect(rail).toContain('app-rail-logo-icon');
    expect(rail).toContain('/brand/texa-mark.svg');
    expect(loading).toContain('./assets/texa-lockup.svg');
    expect(desktopTitleBar).toContain('className="desktop-titlebar-marker"');
    expect(desktopTitleBar).toContain('desktop-window-button');
    expect(desktopMain).toContain("frame: false");
    expect(desktopMain).toContain("'assets', 'texa-taskbar.ico'");
    expect(desktopMain).not.toContain('titleBarOverlay:');
    expect(loading).toContain('loading-window-controls');
    expect(shell).toContain('className="context-sidebar-trigger"');
    expect(learningContext).toContain('className="window-drag-region"');
    expect(chatPage).toContain('className="window-drag-region"');
  });

  it('keeps the exercise workspace toolbar at the shared compact control height', () => {
    expect(exercisesPage).toContain('className="flex h-9 rounded-lg border border-border bg-bg-card p-0.5"');
    expect(exercisesPage).toContain('className="review-toolbar-button app-secondary-button disabled:opacity-50"');
  });

  it('uses a minimal learning empty workspace without duplicate navigation', () => {
    expect(emptyWorkspace).toContain('Ask Texa');
    expect(emptyWorkspace).toContain('输入问题、公式或上传图片');
    expect(emptyWorkspace).not.toContain('其他开始方式');
    expect(emptyWorkspace).not.toContain('随机抽一道题');
    expect(emptyWorkspace).not.toContain('查看今日报告');
  });

  it('reuses the settings model manager in the first-run guide', () => {
    expect(firstRun).toContain('<ModelSettingsManager');
    expect(firstRun).not.toContain('<ModelSettingsForm');
    expect(firstRun).toContain("'/system/settings/model-profiles'");
    expect(firstRun).toContain("'/system/settings/models/test'");
  });

  it('preserves typed ONNX repair states in the Electron startup UI', () => {
    for (const code of [
      'MODEL_MISSING',
      'MODEL_CORRUPT_OR_INCOMPATIBLE',
      'ORT_IMPORT_FAILURE',
      'TOKENIZER_MISMATCH',
    ]) expect(loading).toContain(code);
    expect(loading).toContain('repairEmbedding');
    expect(loading).toContain('修复模型资源');
  });

  it('keeps high-frequency surfaces free of known AI-slop patterns', () => {
    const highFrequencyUi = [firstRun, emptyWorkspace, execution].join('\n');

    expect(highFrequencyUi).not.toContain('Sparkles');
    expect(highFrequencyUi).not.toContain('rounded-[18px]');
    expect(highFrequencyUi).not.toContain('backdrop-blur');
    expect(highFrequencyUi).not.toContain('gradient');
  });
});
