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
import booksImport from './pages/BooksPage.tsx?raw';
import library from './components/settings/LibraryWorkbench.tsx?raw';
import modelSettings from './components/settings/ModelSettingsManager.tsx?raw';
import theme from './theme.ts?raw';
import desktopTitleBar from './components/DesktopTitleBar.tsx?raw';
import desktopMain from '../../desktop/main.cjs?raw';
import loading from '../../desktop/loading.html?raw';
import dialog from './components/ui/Dialog.tsx?raw';
import contextInspector from './components/ui/ContextInspector.tsx?raw';
import settingsDialog from './components/settings/SettingsDialog.tsx?raw';
import scopeSelector from './components/ScopeSelector.tsx?raw';
import figureCatalog from './features/visual-learning/FigureCatalog.tsx?raw';
import figureContextAttachment from './features/visual-learning/FigureContextAttachment.tsx?raw';
import figureViewer from './features/visual-learning/FigureRegionViewer.tsx?raw';

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
    expect(message).toContain('来源已附，段落引用未完全对齐');
    expect(message).toContain("citationProvenance.status !== 'model_aligned'");
    expect(shell).toContain("data-inspector={inspector ? 'open' : 'closed'}");
    expect(shell).toContain('inspectorReplacesContext');
    expect(contextInspector).toContain("window.matchMedia('(max-width: 919.98px)').matches");
    expect(contextInspector).toContain('context-inspector-close');
  });

  it('keeps Figure interruption resumable through the original learning task', () => {
    expect(chatPage).toContain('interruptFigureTask(task.id, partialOutput)');
    expect(chatPage).toContain("task.task_type === 'figure_qa'");
    expect(chatPage).toContain('resumeFigureTaskStream(task.id');
    expect(chatPage).toContain('onResumeInterruptedTask={resumeInterruptedTask}');
  });

  it('separates product navigation from learning context', () => {
    expect(shell).toContain('<AppRail onOpenSettings={openSettings} settingsButtonRef={settingsButtonRef} />');
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

  it('keeps textbook Figure selection inside the Learning Canvas with normalized keyboard-accessible regions', () => {
    expect(chatPage).toContain('<FigureRegionViewer');
    expect(chatPage).toContain('activeFigure && figureWorkspaceExpanded');
    expect(chatPage).toContain('<FigureContextAttachment');
    expect(chatPage).toContain("setFigureWorkspaceExpanded(false)");
    expect(chatPage).toContain("setVisualRegion(null)");
    expect(figureContextAttachment).toContain('继续询问时默认使用整图');
    expect(figureContextAttachment).toContain('查看与框选');
    expect(chatPage).toContain('aria-label="选择教材图片"');
    expect(chatPage).toContain('bookNames={currentScope?.sourceNames?.length ? currentScope.sourceNames : [bookName]}');
    expect(figureCatalog).toContain('Promise.allSettled');
    expect(figureCatalog).toContain("response.status === 'fulfilled'");
    expect(figureViewer).toContain('normalizedPoint');
    expect(figureViewer).toContain('onPointerDown');
    expect(figureViewer).toContain('onKeyDown');
    expect(figureViewer).toContain('Shift + 方向键');
    expect(figureViewer).not.toContain('gradient');
    expect(figureViewer).not.toContain('Sparkles');
  });

  it('uses a semantic, locally persisted appearance theme registry', () => {
    expect(settings).toContain("{ label: '常规', items: [{ id: 'appearance', label: '外观' }] }");
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

  it('opens settings as a focus-managed utility dialog over the current workspace', () => {
    expect(app).toContain('<Navigate to="/" replace state={{ openSettings: true }} />');
    expect(rail).toContain('aria-haspopup="dialog"');
    expect(rail).not.toContain('to="/settings"');
    expect(shell).toContain('<SettingsDialog open={settingsOpen} onClose={closeSettings} />');
    expect(settingsDialog).toContain('className="settings-dialog"');
    expect(settingsDialog).toContain('<SettingsPage />');
    expect(dialog).toContain('role="dialog"');
    expect(dialog).toContain('aria-modal="true"');
    expect(dialog).toContain("event.key === 'Escape'");
    expect(dialog).toContain("event.key !== 'Tab'");
    expect(dialog).toContain('returnFocusRef.current?.focus()');
  });

  it('uses one settings page grammar and keeps commit actions separate from local actions', () => {
    expect(settings).not.toContain('<h2 className="app-page-title">设置</h2>');
    expect(settings).toContain('className="settings-page-header"');
    expect(settings).toContain('className="settings-section"');
    expect(settings).toContain('className="settings-page-actions"');
    expect(settings).toContain('className="app-ghost-button flex-shrink-0"');
    expect(settings).toContain('>保存更改</button>');
  });

  it('renders a question as a lightweight query header with a separate attachment row', () => {
    expect(message).toContain('splitQuestionAttachment');
    expect(message).toContain('className="learning-query-attachment"');
    expect(message).toContain('<span>{questionContent.attachmentName}</span>');
    expect(message).not.toContain("{isUser ? '问题' : '回答'}");
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
    expect(emptyWorkspace).toContain('<h1>Ask Texa</h1>');
    expect(emptyWorkspace).toContain('输入问题、公式或上传图片');
    expect(emptyWorkspace).not.toContain('learning-empty-context');
    expect(emptyWorkspace).not.toContain('scopeContainsBook');
    expect(emptyWorkspace).not.toContain('其他开始方式');
    expect(emptyWorkspace).not.toContain('随机抽一道题');
    expect(emptyWorkspace).not.toContain('查看今日报告');
  });

  it('centers the existing composer with the prompt only before the first message', () => {
    expect(chatPage).toContain("data-empty={messages.length === 0 && !activeFigure ? 'true' : 'false'}");
    expect(chatPage.match(/className="chat-composer"/g)).toHaveLength(1);
  });

  it('reuses the settings model manager in the first-run guide', () => {
    expect(firstRun).toContain('<ModelSettingsManager');
    expect(firstRun).not.toContain('<ModelSettingsForm');
    expect(firstRun).toContain("'/system/settings/model-profiles'");
    expect(firstRun).toContain("'/system/settings/models/test'");
  });

  it('presents shared and independent vision handling without internal architecture terms', () => {
    expect(modelSettings).toContain('使用推理模型');
    expect(modelSettings).toContain('使用独立视觉模型');
    expect(modelSettings).toContain("value.multimodal_mode === 'native' ? ['vision'] : ['reasoning', 'vision']");
    expect(modelSettings).not.toContain('ProviderRail');
    expect(modelSettings).not.toContain('集成回复');
    expect(modelSettings).not.toContain('识图模型直接解答');
  });

  it('reuses the shared scrollable select for every model-settings list', () => {
    expect(modelSettings.match(/<ScrollableSelect/g)).toHaveLength(4);
    expect(modelSettings).toContain('showSelectedDescription={false}');
    expect(modelSettings).toContain("label: '添加自定义模型…'");
    expect(modelSettings).toContain('显示名称');
    expect(modelSettings).toContain('placeholder="例如：qwen3.7-plus"');
    expect(modelSettings.match(/\n\s+compact\n/g)).toHaveLength(4);
    expect(modelSettings).not.toContain('仅用于在 Texa 中显示');
    expect(modelSettings).not.toContain('通常由小写字母');
    expect(modelSettings).not.toContain('<select');
  });

  it('keeps textbook parsing outside the model-provider flow', () => {
    expect(settings).toContain("{ id: 'ingestion', label: '教材解析' }");
    expect(settings).toContain('配置教材导入时使用的 MinerU 文档解析服务');
    expect(settings).not.toContain('这些设置独立于模型 Provider');
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

  it('keeps textbook readiness actionable without overstating semantic quality', () => {
    expect(library).toContain('索引与 IR');
    expect(library).toContain('<b>检索</b>');
    expect(library).toContain('<b>IR</b>');
    expect(library).toContain('语义质量尚未人工验证');
    expect(library).not.toContain('未验证，不等同答案准确');
    expect(library).toContain('重索引');
    expect(settings).toContain('/reindex');
  });

  it('keeps textbook management as a dense workbench with inline category editing and archive filtering', () => {
    expect(settings).toContain('library-page-main');
    expect(settings).toContain('<LibraryWorkbench');
    expect(library).toContain('library-workbench');
    expect(library).toContain('renamingCategory');
    expect(library).toContain("useState<'active' | 'archived'>('active')");
    expect(library).toContain('library-list-columns');
    expect(library).not.toContain('回答时优先参考。');
    expect(library).not.toContain('用于补充主要教材的内容。');
  });

  it('reuses the managed subject hierarchy for textbook assignment', () => {
    expect(library).toContain('<ScopeSelector');
    expect(library).toContain('subjectTree={subjects}');
    expect(library).toContain('bookMode="hidden"');
    expect(library).not.toContain('<ScrollableSelect');
    expect(scopeSelector).toContain('subjectTree?: ScopeSubjectNode[]');
    expect(scopeSelector).toContain('if (subjectTree) return;');
  });

  it('keeps one library toolbar and dismisses non-error health feedback', () => {
    expect(settings).toContain('library-page-heading');
    expect(settings).toContain('app-page-header border-b border-border bg-bg-primary');
    expect(settings).not.toContain('教材管理</h2>');
    expect(settings).toContain("window.setTimeout(() => setMessage(''), 3600)");
    expect(settings).toContain("['available', 'downloading', 'downloaded', 'installing', 'error']");
    expect(settings).toContain("/开发模式|不执行自动更新|无需更新|最新版本/");
    expect(settings).toContain("feedbackKind(version.message) === 'error'");
  });

  it('checks MinerU before selecting it and exposes the output-bundle fallback', () => {
    expect(booksImport).toContain('/books/import-capabilities');
    expect(booksImport).toContain("useState<'mineru' | 'local'>('local')");
    expect(booksImport).toContain('MinerU 当前不可用');
    expect(booksImport).toContain('转到 MinerU 输出包');
  });

  it('keeps high-frequency surfaces free of known AI-slop patterns', () => {
    const highFrequencyUi = [firstRun, emptyWorkspace, execution].join('\n');

    expect(highFrequencyUi).not.toContain('Sparkles');
    expect(highFrequencyUi).not.toContain('rounded-[18px]');
    expect(highFrequencyUi).not.toContain('backdrop-blur');
    expect(highFrequencyUi).not.toContain('gradient');
  });
});
