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
import composerOverflow from './components/chat/ComposerOverflowMenu.tsx?raw';
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

  it('keeps the composer as one responsive surface with an internal overflow menu', () => {
    expect(chatPage).toContain('className="composer-surface"');
    expect(chatPage).toContain('className="composer-toolbar"');
    expect(composerOverflow).toContain('className="composer-overflow-menu"');
    expect(composerOverflow).toContain('aria-label="更多"');
    expect(composerOverflow).toContain("event.key !== 'Escape'");
    expect(composerOverflow).toContain("document.addEventListener('pointerdown'");
    expect(chatPage).toContain('aria-label="发送问题"');
    expect(chatPage).not.toContain('chat-toolbar mx-auto');
  });

  it('renders a question as a lightweight query header with a separate attachment row', () => {
    expect(message).toContain('splitQuestionAttachment');
    expect(message).toContain('className="learning-query-attachment"');
    expect(message).toContain('附件：{questionContent.attachmentName}');
  });

  it('shares one desktop header geometry and preserves native resize hit areas', () => {
    expect(rail).toContain('app-rail-logo-icon');
    expect(desktopTitleBar).toContain('className="desktop-titlebar-marker"');
    expect(desktopMain).toContain("titleBarStyle: 'hidden'");
    expect(desktopMain).toContain('titleBarOverlay:');
    expect(desktopMain).not.toContain('frame: false');
    expect(loading).not.toContain('loading-window-controls');
    expect(shell).toContain('className="context-sidebar-trigger"');
    expect(learningContext).toContain('className="window-drag-region"');
    expect(chatPage).toContain('className="window-drag-region"');
  });

  it('uses a minimal learning empty workspace without duplicate navigation', () => {
    expect(emptyWorkspace).toContain('Ask Texa');
    expect(emptyWorkspace).toContain('输入问题、公式或上传图片');
    expect(emptyWorkspace).not.toContain('其他开始方式');
    expect(emptyWorkspace).not.toContain('随机抽一道题');
    expect(emptyWorkspace).not.toContain('查看今日报告');
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
