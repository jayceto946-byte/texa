import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, BookOpen, CheckCircle2, CircleX, RefreshCw, Save } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { del, get, patch, post } from '../api/client';
import { useSystemHealth } from '../hooks/useSystemHealth';
import { useChatContext } from '../contexts/ChatContext';
import type { SystemHealthStatus } from '../types';
import LibraryWorkbench, { type LibraryBook } from './settings/LibraryWorkbench';
import DataSafety from './settings/DataSafety';
import MobileRemoteS0 from './settings/MobileRemoteS0';
import AppearanceSettings from './settings/AppearanceSettings';
import type { ModelSettingsValue } from './settings/ModelSettingsForm';
import ModelSettingsManager from './settings/ModelSettingsManager';
import { PageState, StatusBanner, type AsyncStateKind } from './ui/AsyncState';

type SubjectNode = { name: string; children: string[] };
type ManagedBook = LibraryBook & { size?: number };
type Tab = 'diagnostics' | 'about' | 'data' | 'subjects' | 'models' | 'preferences';

const statusMeta: Record<SystemHealthStatus, { label: string; icon: typeof CheckCircle2; iconClass: string; className: string }> = {
  healthy: { label: '系统正常', icon: CheckCircle2, iconClass: 'text-[var(--success)]', className: 'status-success' },
  degraded: { label: '部分降级', icon: AlertTriangle, iconClass: 'text-[var(--warning)]', className: 'status-warning' },
  error: { label: '系统异常', icon: CircleX, iconClass: 'text-[var(--danger)]', className: 'border-red-300 bg-red-50 text-[var(--danger)]' },
};

const componentLabels: Record<string, string> = { embedding_runtime: '本地嵌入模型', vector_store: '向量检索', mistake_book: '错题库', rag_trace: '检索记录', runtime_config: '模型连接', exercise_bank: '习题库' };

function componentMessage(key: string, message = '') {
  if (key === 'runtime_config' && /LLM configuration is ready/i.test(message)) return '模型配置已就绪';
  if (key === 'embedding_runtime' && /ONNX embedding runtime is ready/i.test(message)) return '本地嵌入模型可用';
  return message;
}

function feedbackKind(message: string): AsyncStateKind {
  if (/失败|异常|错误|不可用/.test(message)) return 'error';
  if (/正在|检查中|下载中|安装中/.test(message)) return 'loading';
  if (/开发模式|不执行自动更新|无需更新|最新版本/.test(message)) return 'info';
  return 'success';
}
const SETTINGS_ITEMS: Array<{ id: Tab; label: string }> = [
  { id: 'preferences', label: '偏好' },
  { id: 'models', label: '模型连接' },
  { id: 'data', label: '数据与教材' },
  { id: 'about', label: '关于与更新' },
];

function subjectPath(parent?: string, child?: string) {
  const p = (parent || '').trim();
  const c = (child || '').trim();
  if (!p) return c;
  return c ? `${p}/${c}` : p;
}

function bookBelongsTo(book: ManagedBook, parent: string, child = '') {
  const value = (book.subject || '').trim();
  if (!parent) return !value;
  if (child) return value === subjectPath(parent, child) || value === child;
  return value === parent || value.startsWith(`${parent}/`);
}

const SettingsPage: React.FC<{ standaloneTab?: 'subjects'; open?: boolean; onModelDirtyChange?: (dirty: boolean) => void }> = ({ standaloneTab, open = true, onModelDirtyChange }) => {
  const { bookName, setBookName, setSubject } = useChatContext();
  const [tab, setTab] = useState<Tab>(standaloneTab || 'preferences');
  const { health, loading, loadHealth } = useSystemHealth(bookName, open && !standaloneTab && tab === 'diagnostics');
  const navigate = useNavigate();
  const [version, setVersion] = useState<any>(null);
  const [subjects, setSubjects] = useState<SubjectNode[]>([]);
  const [books, setBooks] = useState<ManagedBook[]>([]);
  const [bookDrafts, setBookDrafts] = useState<Record<string, string>>({});
  const [envDraft, setEnvDraft] = useState<Record<string, string>>({});
  const [modelDraft, setModelDraft] = useState<ModelSettingsValue | null>(null);
  const [savedModel, setSavedModel] = useState<ModelSettingsValue | null>(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [savingModel, setSavingModel] = useState(false);
  const [desktopUpdate, setDesktopUpdate] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [feedback, setFeedback] = useState<Partial<Record<Tab, string>>>({});
  const pageMessage = feedback[tab] || '';
  const showFeedback = (value: string) => setFeedback((current) => ({ ...current, [tab]: value }));
  const [selectedSubjectIndex, setSelectedSubjectIndex] = useState(0);
  const [selectedChildIndex, setSelectedChildIndex] = useState<number | null>(null);
  const [reindexingBook, setReindexingBook] = useState('');

  const loadSettings = useCallback(async () => {
    const res = await get('/system/settings', 20000);
    if (!res?.success) throw new Error(res?.message || '设置加载失败');
    setFeedback((current) => ({ ...current, models: current.models === '设置加载失败' ? '' : current.models, data: current.data === '设置加载失败' ? '' : current.data }));
    setSettingsLoaded(true);
    if (!standaloneTab) {
      setModelDraft(res.data.models || null);
      setSavedModel(res.data.models || null);
    }
    if (standaloneTab) setSubjects(res.data.subjects || []);
    const env = res.data.env || {};
    if (!settingsLoaded) setEnvDraft({
      MINERU_API_URL: env.MINERU_API_URL?.value || '',
      MINERU_CLI_COMMAND: env.MINERU_CLI_COMMAND?.value || '',
    });
  }, [standaloneTab, settingsLoaded]);

  const loadVersion = useCallback(async () => {
    const res = await get('/system/version', 15000);
    if (res?.success) setVersion(res.data);
  }, []);

  const loadBooks = useCallback(async () => {
    const res = await get('/books/list?include_archived=true', 20000);
    if (!res?.success) return;
    const nextBooks: ManagedBook[] = res.data || [];
    setBooks(nextBooks);
    setBookDrafts(Object.fromEntries(nextBooks.map((book) => [book.name, book.subject || ''])));
  }, []);

  useEffect(() => {
    if (!open || settingsLoaded || (!standaloneTab && tab !== 'models' && tab !== 'data')) return;
    loadSettings().catch(() => standaloneTab ? setMessage('设置加载失败') : setFeedback((current) => ({ ...current, [tab]: '设置加载失败' })));
  }, [open, standaloneTab, settingsLoaded, tab, loadSettings]);

  useEffect(() => {
    if (standaloneTab) loadBooks().catch(() => undefined);
  }, [standaloneTab, loadBooks]);

  useEffect(() => {
    if (open && !standaloneTab && (tab === 'about' || tab === 'diagnostics')) loadVersion().catch(() => undefined);
  }, [open, standaloneTab, tab, loadVersion]);

  useEffect(() => {
    if (!open || standaloneTab || tab !== 'about' || !window.kaoyanDesktop?.getUpdateStatus) return;
    let mounted = true;
    window.kaoyanDesktop.getUpdateStatus().then((status) => { if (mounted) setDesktopUpdate(status); }).catch(() => undefined);
    const unsubscribe = window.kaoyanDesktop.onUpdateStatus?.((status) => setDesktopUpdate(status));
    return () => {
      mounted = false;
      unsubscribe?.();
    };
  }, [open, standaloneTab, tab]);

  useEffect(() => {
    if (!message) return;
    const kind = feedbackKind(message);
    if (kind === 'error' || kind === 'loading') return;
    const timer = window.setTimeout(() => setMessage(''), 3600);
    return () => window.clearTimeout(timer);
  }, [message]);

  useEffect(() => {
    if (selectedSubjectIndex < 0) return;
    if (!subjects.length) {
      setSelectedSubjectIndex(0);
      setSelectedChildIndex(null);
      return;
    }
    if (selectedSubjectIndex >= subjects.length) {
      setSelectedSubjectIndex(Math.max(0, subjects.length - 1));
      setSelectedChildIndex(null);
      return;
    }
    const childCount = subjects[selectedSubjectIndex]?.children?.length || 0;
    if (selectedChildIndex !== null && selectedChildIndex >= childCount) setSelectedChildIndex(null);
  }, [subjects, selectedSubjectIndex, selectedChildIndex]);

  const status = health?.status || 'degraded';
  const meta = statusMeta[status];
  const StatusIcon = meta.icon;
  const selectedSubject = subjects[selectedSubjectIndex] || null;
  const selectedChild = selectedSubject && selectedChildIndex !== null ? selectedSubject.children[selectedChildIndex] || '' : '';
  const targetSubject = subjectPath(selectedSubject?.name, selectedChild);
  const persistentUpdateMessage = desktopUpdate
    ? (['available', 'downloading', 'downloaded', 'installing', 'error'].includes(desktopUpdate.status) ? desktopUpdate.message : '')
    : version?.message && feedbackKind(version.message) === 'error' ? version.message : '';


  const modelDirty = Boolean(modelDraft && savedModel && JSON.stringify(modelDraft) !== JSON.stringify(savedModel));
  const nativeModel = modelDraft?.models.find((item) => item.provider === modelDraft.roles.vision.provider && item.id === modelDraft.roles.vision.model);
  const nativeProvider = modelDraft?.providers.find((item) => item.id === modelDraft.roles.vision.provider);
  const nativeUnsupported = modelDraft?.multimodal_mode === 'native' && (!nativeProvider?.capabilities.includes('vision') || (nativeModel && !nativeModel.capabilities.includes('vision')));
  useEffect(() => { onModelDirtyChange?.(modelDirty); }, [modelDirty, onModelDirtyChange]);
  useEffect(() => {
    if (!open && savedModel) setModelDraft(savedModel);
  }, [open, savedModel]);
  const saveModels = async () => {
    if (!modelDraft || savingModel || !modelDirty || nativeUnsupported) return;
    setSavingModel(true);
    showFeedback('');
    try {
    const res = await post('/system/settings/model-profiles', {
      activate: true,
      profile: { ...modelDraft, id: modelDraft.editing_profile_id, name: modelDraft.profile_name },
    }, 20000);
    showFeedback(res?.message || (res?.success ? '模型方案已保存并应用' : '保存失败'));
    if (res?.success) await loadSettings();
    } catch { showFeedback('保存失败，请检查本地服务后重试'); }
    finally { setSavingModel(false); }
  };

  const saveIngestion = async () => {
    if (!settingsLoaded) return;
    showFeedback('');
    try {
      const res = await post('/system/settings/env', envDraft, 20000);
      showFeedback(res?.message || (res?.success ? '教材解析配置已保存' : '保存失败'));
    } catch { showFeedback('保存失败，请检查本地服务后重试'); }
  };

  const activateModelProfile = async (profileId: string) => {
    if (modelDirty && !window.confirm('当前模型配置有未保存更改。放弃更改并切换方案吗？')) return;
    showFeedback('');
    const res = await post(`/system/settings/model-profiles/${encodeURIComponent(profileId)}/activate`, {}, 20000);
    showFeedback(res?.message || (res?.success ? '模型方案已切换并应用' : '切换失败'));
    if (res?.success) { setModelDraft(res.data as ModelSettingsValue); setSavedModel(res.data as ModelSettingsValue); }
  };

  const deleteModelProfile = async (profileId: string) => {
    if (!window.confirm('删除这个模型方案吗？已保存的 API Key 不会被删除。')) return;
    const res = await del(`/system/settings/model-profiles/${encodeURIComponent(profileId)}`, 20000);
    showFeedback(res?.message || (res?.success ? '模型方案已删除' : '删除失败'));
    if (res?.success) { setModelDraft(res.data as ModelSettingsValue); setSavedModel(res.data as ModelSettingsValue); }
  };

  const testModelConnection = async (role: 'reasoning' | 'vision') => {
    if (!modelDraft) return { success: false, message: '模型配置尚未加载' };
    try {
      const res = await post('/system/settings/models/test', { role, settings: modelDraft }, 30000);
      return { success: Boolean(res?.success), message: res?.success ? '连接成功' : '连接失败，请检查服务地址、模型和凭证' };
    } catch {
      return { success: false, message: '连接失败，请检查服务地址、模型和凭证' };
    }
  };

  const saveSubjects = async (next = subjects) => {
    setMessage('');
    const cleaned = next
      .map((item) => ({ name: item.name.trim(), children: item.children.map((child) => child.trim()).filter(Boolean) }))
      .filter((item) => item.name);
    const res = await post('/system/settings/subjects', { subjects: cleaned }, 20000);
    setMessage(res?.message || (res?.success ? '已保存学科' : '学科保存失败'));
    if (res?.success) setSubjects(res.data || cleaned);
  };

  const addSubject = () => {
    const nextIndex = subjects.length;
    setSubjects((prev) => [...prev, { name: `新学科 ${nextIndex + 1}`, children: [] }]);
    setSelectedSubjectIndex(nextIndex);
    setSelectedChildIndex(null);
  };

  const addChild = (subjectIndex = selectedSubjectIndex) => {
    const subject = subjects[subjectIndex];
    if (!subject) return;
    const childIndex = subject.children.length;
    setSubjects((prev) => prev.map((item, index) => index === subjectIndex ? { ...item, children: [...item.children, '新科目 ' + (childIndex + 1)] } : item));
    setSelectedSubjectIndex(subjectIndex);
    setSelectedChildIndex(childIndex);
  };

  const updateSubjectName = (index: number, name: string) => setSubjects((prev) => prev.map((item, i) => i === index ? { ...item, name } : item));
  const updateChildName = (childIndex: number, name: string) => setSubjects((prev) => prev.map((item, i) => i === selectedSubjectIndex ? { ...item, children: item.children.map((child, ci) => ci === childIndex ? name : child) } : item));

  const deleteSubject = (index: number) => {
    const subject = subjects[index];
    if (subject && books.some((book) => bookBelongsTo(book, subject.name))) { setMessage('该学科仍有教材，请先移动教材。'); return; }
    if (!window.confirm('删除空学科目录吗？教材文件、索引和学习记录不会被改动。')) return;
    setSubjects((prev) => prev.filter((_, i) => i !== index));
    setSelectedSubjectIndex(0);
    setSelectedChildIndex(null);
  };

  const deleteChild = (childIndex: number) => {
    const child = selectedSubject?.children[childIndex] || '';
    if (selectedSubject && books.some((book) => bookBelongsTo(book, selectedSubject.name, child))) { setMessage('该科目仍有教材，请先移动教材。'); return; }
    if (!window.confirm('删除空科目目录吗？教材文件、索引和学习记录不会被改动。')) return;
    setSubjects((prev) => prev.map((item, index) => index === selectedSubjectIndex ? { ...item, children: item.children.filter((_, i) => i !== childIndex) } : item));
    setSelectedChildIndex(null);
  };

  const saveBookSubject = async (name: string, overrideSubject?: string) => {
    setMessage('');
    const nextSubject = overrideSubject ?? bookDrafts[name] ?? '';
    const res = await patch(`/books/${encodeURIComponent(name)}`, { subject: nextSubject }, 20000);
    setMessage(res?.message || (res?.success ? '教材学科已保存' : '教材保存失败'));
    if (res?.success) {
      await loadBooks();
      window.dispatchEvent(new Event('books:changed'));
    }
  };

  const moveBookToTarget = async (name: string, nextTarget = targetSubject) => {
    await saveBookSubject(name, nextTarget);
  };

  const deleteManagedBook = async (name: string) => {
    if (!window.confirm('这会把教材从管理列表隐藏，但不会删除本地文件、章节索引、向量库或学习记录。继续吗？')) return;
    setMessage('');
    const res = await del(`/books/${encodeURIComponent(name)}`, 20000);
    setMessage(res?.message || (res?.success ? '教材已隐藏' : '教材删除失败'));
    if (res?.success) {
      await loadBooks();
      window.dispatchEvent(new Event('books:changed'));
    }
  };

  const renameManagedBook = async (name: string, currentDisplayName: string) => {
    const next = window.prompt('教材展示名称（不会移动文件、数据库或索引）', currentDisplayName)?.trim();
    if (!next || next === currentDisplayName) return;
    setMessage('');
    const res = await patch(`/books/${encodeURIComponent(name)}`, { display_name: next }, 20000);
    setMessage(res?.message || (res?.success ? '教材名称已更新' : '教材重命名失败'));
    if (res?.success) {
      await loadBooks();
      window.dispatchEvent(new Event('books:changed'));
    }
  };

  const restoreManagedBook = async (reference: string) => {
    setMessage('');
    const res = await post(`/books/${encodeURIComponent(reference)}/restore`, {}, 20000);
    setMessage(res?.message || (res?.success ? '教材已恢复' : '教材恢复失败'));
    if (res?.success) {
      await loadBooks();
      window.dispatchEvent(new Event('books:changed'));
    }
  };
  const setBookRole = async (name: string, role: 'standalone' | 'core' | 'reference') => {
    setMessage('');
    const res = await patch(`/books/${encodeURIComponent(name)}`, { book_role: role }, 20000);
    setMessage(res?.message || (res?.success ? '教材检索角色已保存' : '检索角色保存失败'));
    if (res?.success) {
      await loadBooks();
      window.dispatchEvent(new Event('books:changed'));
    }
  };

  const setBookResourceGroup = async (name: string, resourceGroup: string) => {
    setMessage('');
    const res = await patch(`/books/${encodeURIComponent(name)}`, { resource_group: resourceGroup }, 20000);
    setMessage(res?.message || (res?.success ? '教材检索组已保存' : '检索组保存失败'));
    if (res?.success) {
      await loadBooks();
      window.dispatchEvent(new Event('books:changed'));
    }
  };

  const switchManagedBook = async (name: string) => {
    setMessage('');
    const res = await get(`/books/switch/${encodeURIComponent(name)}`, 20000);
    if (!res?.success) {
      setMessage(res?.message || '切换教材失败');
      return;
    }
    setBookName(res.data?.name || name);
    if (res.data?.subject) setSubject(res.data.subject);
    setMessage('已更新当前学习范围');
  };

  const openBookImport = () => {
    navigate('/books/import');
  };

  const reindexManagedBook = async (name: string) => {
    if (reindexingBook) return;
    setReindexingBook(name);
    setMessage(`正在重新准备《${name}》…`);
    try {
      const res = await post(`/books/${encodeURIComponent(name)}/reindex`, {}, 10 * 60 * 1000);
      setMessage(res?.success ? '教材已重新准备，可以继续学习' : (res?.message || '教材准备失败'));
      if (res?.success) {
        await loadBooks();
        window.dispatchEvent(new Event('books:changed'));
      }
    } catch (error) {
      setMessage(error instanceof Error ? `教材准备失败：${error.message}` : '教材准备失败');
    } finally {
      setReindexingBook('');
    }
  };

  const reloadVectorStore = async () => {
    showFeedback('正在重载向量库...');
    const res = await post('/system/vector-store/reload', {}, 90000);
    showFeedback(res?.message || (res?.success ? '向量库已重载' : '向量库重载失败'));
    await loadHealth();
  };

  const updateApp = async () => {
    showFeedback('');
    if (window.kaoyanDesktop?.checkForUpdates) {
      const res = await window.kaoyanDesktop.checkForUpdates();
      setDesktopUpdate(res);
      showFeedback(res?.message || '更新检查完成');
      return;
    }
    showFeedback('当前运行方式不支持桌面自动更新，请在 Electron 桌面端检查。');
  };

  const downloadUpdate = async () => {
    showFeedback('');
    const res = await window.kaoyanDesktop?.downloadUpdate?.();
    if (res) {
      setDesktopUpdate(res);
      showFeedback(res.message || '开始下载更新');
    }
  };

  const installUpdate = async () => {
    showFeedback('');
    const res = await window.kaoyanDesktop?.installUpdate?.();
    if (res) {
      setDesktopUpdate(res);
      showFeedback(res.message || '正在安装更新');
    }
  };
  if (standaloneTab === 'subjects') {
    return (
      <div className="management-workspace flex h-full min-w-0 flex-col bg-bg-primary">
        <header className="app-page-header border-b border-border bg-bg-primary">
          <div className="library-page-heading">
             <h2 className="app-page-title">教材</h2>
          </div>
          <div className="library-page-actions">
            <button onClick={() => saveSubjects()} className="app-secondary-button"><Save className="h-4 w-4" />保存目录</button>
            <button onClick={openBookImport} className="app-primary-button"><BookOpen className="h-4 w-4" />导入教材</button>
          </div>
        </header>
        <main className="library-page-main min-h-0 min-w-0 flex-1">
          {message && <div className="library-transient-feedback"><StatusBanner kind={feedbackKind(message)} title={message} /></div>}
          <LibraryWorkbench
            subjects={subjects}
            books={books}
            selectedSubjectIndex={selectedSubjectIndex}
            selectedChildIndex={selectedChildIndex}
            onSelect={(subjectIndex, childIndex) => { setSelectedSubjectIndex(subjectIndex); setSelectedChildIndex(childIndex); }}
            onAddSubject={addSubject}
            onAddChild={addChild}
            onRenameSubject={updateSubjectName}
            onRenameChild={updateChildName}
            onDeleteSubject={deleteSubject}
            onDeleteChild={deleteChild}
            onRefresh={loadBooks}
            onMoveBook={moveBookToTarget}
            onSwitchBook={switchManagedBook}
            onArchiveBook={deleteManagedBook}
            onRestoreBook={restoreManagedBook}
            onRenameBook={renameManagedBook}
            onSetRole={setBookRole}
            onSetResourceGroup={setBookResourceGroup}
            onReindexBook={reindexManagedBook}
            reindexingBook={reindexingBook}
            currentBookName={bookName}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="settings-dialog-body">
      <SettingsSidebar tab={tab} onTabChange={(nextTab) => { setTab(nextTab); }} />
      <main className="settings-content-pane">
        {pageMessage && <div className="mb-5"><StatusBanner kind={feedbackKind(pageMessage)} title={pageMessage} /></div>}

        {tab === 'about' && <MobileRemoteS0 />}
        {tab === 'diagnostics' && (
          <section className="settings-page">
            <SettingsPageHeader title="高级与诊断" description="检查本地服务与数据组件的运行状态。" />
            {loading && !health && <PageState kind="loading" title="正在检查系统状态" />}
            <section className="settings-section" aria-labelledby="health-status-heading">
              <div className="settings-section-header">
                <div>
                  <h4 id="health-status-heading" className="settings-section-title">系统状态</h4>
                  <div className="mt-2 flex items-center gap-2 settings-row-title"><StatusIcon className={`h-4 w-4 ${meta.iconClass}`} />{meta.label}</div>
                </div>
                <button onClick={loadHealth} className="app-secondary-button"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />重新检查</button>
              </div>
              <div className="settings-row-list">
                {health && Object.entries(health.components).map(([key, item]) => {
                  const itemMeta = statusMeta[item.status] || statusMeta.degraded;
                  const ItemIcon = itemMeta.icon;
                  return (
                    <div key={key} className="settings-row">
                      <ItemIcon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${itemMeta.iconClass}`} />
                      <div className="min-w-0 flex-1">
                        <div className="settings-row-title">{componentLabels[key] || '系统组件'}</div>
                        <div className="mt-1 settings-secondary">{componentMessage(key, item.message)}</div>
                      </div>
                      {key === 'vector_store' && <button type="button" onClick={reloadVectorStore} className="app-ghost-button flex-shrink-0"><RefreshCw className="h-3.5 w-3.5" />重载</button>}
                    </div>
                  );
                })}
              </div>
            </section>
            <details className="settings-section"><summary className="settings-secondary cursor-pointer">开发信息</summary><dl className="settings-definition-list"><div><dt>分支</dt><dd>{version?.branch || '未知'}</dd></div><div><dt>提交</dt><dd className="font-mono">{version?.commit || '未知'}</dd></div></dl></details>
          </section>
        )}

        {tab === 'about' && (
          <section className="settings-page">
            <SettingsPageHeader title="关于与更新" description="查看应用版本与更新状态。" />
            <section className="settings-section" aria-labelledby="version-current-heading">
              <h4 id="version-current-heading" className="settings-section-title">当前版本</h4>
              <dl className="settings-definition-list">
                <div><dt>版本</dt><dd>{desktopUpdate?.currentVersion || version?.version || '未知'}</dd></div>
              </dl>
              {persistentUpdateMessage && <p className="settings-secondary">{persistentUpdateMessage}</p>}
              <p className="settings-secondary">本软件使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.</p>
              {desktopUpdate?.updateInfo?.version && <div className="status-success workspace-radius workspace-interface-text border p-3">可更新到 {desktopUpdate.updateInfo.version}</div>}
              {desktopUpdate?.status === 'downloading' && (
                <div>
                  <div className="mb-2 flex justify-between settings-secondary"><span>下载进度</span><span>{Math.round(desktopUpdate?.progress?.percent || 0)}%</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-bg-secondary"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(desktopUpdate?.progress?.percent || 0)}%` }} /></div>
                </div>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                {window.kaoyanDesktop?.checkForUpdates ? desktopUpdate?.status === 'downloaded' ? <button onClick={installUpdate} className="app-primary-button">重启安装</button> : desktopUpdate?.status === 'available' ? <button onClick={downloadUpdate} className="app-primary-button">下载更新</button> : <button onClick={updateApp} disabled={['checking', 'downloading', 'installing'].includes(desktopUpdate?.status)} className="app-primary-button">{desktopUpdate?.status === 'checking' ? '检查中' : '检查更新'}</button> : <p className="settings-secondary">当前运行方式不支持桌面自动更新。</p>}
              </div>
            </section>
          </section>
        )}

        {tab === 'data' && <section className="settings-page">
          <SettingsPageHeader title="数据与教材" description="备份学习数据，配置教材解析。" />
          <DataSafety />
          {!settingsLoaded && <PageState kind={pageMessage ? 'error' : 'loading'} title={pageMessage || '正在读取解析配置'} />}
          {!settingsLoaded && pageMessage && <button type="button" className="app-secondary-button" onClick={() => void loadSettings().then(() => showFeedback('')).catch(() => showFeedback('设置加载失败'))}>重试</button>}
          {settingsLoaded &&
          <section className="settings-section" aria-labelledby="ingestion-service-heading">
            <h4 id="ingestion-service-heading" className="settings-section-title">教材解析服务</h4>
            <p className="settings-secondary">导入扫描教材时使用 MinerU。服务地址仅在解析时使用。</p>
            <Field label="MinerU API URL"><input value={envDraft.MINERU_API_URL || ''} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_API_URL: e.target.value })} placeholder="http://127.0.0.1:9001" className="settings-input" /></Field>
            <details><summary className="settings-secondary cursor-pointer">本地命令（可选）</summary><div className="mt-3"><Field label="MinerU CLI"><input value={envDraft.MINERU_CLI_COMMAND || ''} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_CLI_COMMAND: e.target.value })} placeholder="mineru -p {input} -o {output}" className="settings-input" /></Field></div></details>
            <div><button onClick={saveIngestion} className="app-secondary-button"><Save className="h-4 w-4" />保存解析配置</button></div>
          </section>}
        </section>}


        {tab === 'preferences' && <section className="settings-page"><SettingsPageHeader title="偏好" description="调整当前设备的阅读外观。" /><AppearanceSettings /></section>}

        {tab === 'models' && (
          <section className="settings-page">
            <SettingsPageHeader title="模型连接" description="管理回答与识图模型。凭证保存在本机，连接测试会访问所选服务。" />
            {modelDraft ? <ModelSettingsManager value={modelDraft} onChange={setModelDraft} onActivateProfile={activateModelProfile} onDeleteProfile={deleteModelProfile} onTestConnection={testModelConnection} /> : <PageState kind={pageMessage ? 'error' : 'loading'} title={pageMessage || '正在读取模型配置'} />}
            {!modelDraft && pageMessage && <button type="button" className="app-secondary-button" onClick={() => void loadSettings().then(() => showFeedback('')).catch(() => showFeedback('设置加载失败'))}>重试</button>}
            <div className="settings-page-actions">{modelDirty && <><span className="settings-secondary" role="status">{nativeUnsupported ? '当前单模型不支持识图，请更换模型' : '未保存更改'}</span><button type="button" onClick={() => savedModel && setModelDraft(savedModel)} className="app-secondary-button">放弃更改</button><button onClick={saveModels} disabled={savingModel || nativeUnsupported} className="app-primary-button"><Save className="h-4 w-4" />{savingModel ? "保存中…" : "保存并应用"}</button></>}</div>
          </section>
        )}


      </main>
    </div>
  );
};

const SettingsSidebar = ({ tab, onTabChange }: { tab: Tab; onTabChange: (tab: Tab) => void }) => (
  <aside className="settings-sidebar" aria-label="设置分类">
    <div className="settings-sidebar-groups">
      <div className="settings-nav-items">{SETTINGS_ITEMS.map((item) => (
        <button type="button" key={item.id} onClick={() => onTabChange(item.id)} className={`settings-nav-item ${tab === item.id ? 'is-active' : ''}`} aria-current={tab === item.id ? 'page' : undefined}>{item.label}</button>
      ))}</div>
      <button type="button" onClick={() => onTabChange('diagnostics')} className={`settings-nav-item settings-nav-diagnostics ${tab === 'diagnostics' ? 'is-active' : ''}`} aria-current={tab === 'diagnostics' ? 'page' : undefined}>高级与诊断</button>
    </div>
  </aside>
);

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="settings-form-row"><span className="settings-label">{label}</span><span className="block min-w-0">{children}</span></label>
);

const SettingsPageHeader = ({ title, description }: { title: string; description: string }) => (
  <header className="settings-page-header"><h3>{title}</h3><p>{description}</p></header>
);

export default SettingsPage;
