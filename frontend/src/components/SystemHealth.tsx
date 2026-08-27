import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, BookOpen, CheckCircle2, CircleX, RefreshCw, Save } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { del, get, patch, post } from '../api/client';
import { useSystemHealth } from '../hooks/useSystemHealth';
import { useChatContext } from '../contexts/ChatContext';
import type { SystemHealthStatus } from '../types';
import LibraryWorkbench, { type LibraryBook } from './settings/LibraryWorkbench';
import DataSafety from './settings/DataSafety';
import AppearanceSettings from './settings/AppearanceSettings';
import type { ModelSettingsValue } from './settings/ModelSettingsForm';
import ModelSettingsManager from './settings/ModelSettingsManager';
import { PageState, StatusBanner, type AsyncStateKind } from './ui/AsyncState';

type SubjectNode = { name: string; children: string[] };
type ManagedBook = LibraryBook & { size?: number };
type Tab = 'health' | 'version' | 'data' | 'subjects' | 'models' | 'appearance' | 'ingestion';

const statusMeta: Record<SystemHealthStatus, { label: string; icon: typeof CheckCircle2; iconClass: string; className: string }> = {
  healthy: { label: '系统正常', icon: CheckCircle2, iconClass: 'text-[var(--success)]', className: 'status-success' },
  degraded: { label: '部分降级', icon: AlertTriangle, iconClass: 'text-[var(--warning)]', className: 'status-warning' },
  error: { label: '系统异常', icon: CircleX, iconClass: 'text-[var(--danger)]', className: 'border-red-300 bg-red-50 text-[var(--danger)]' },
};

const componentLabels: Record<string, string> = { vector_store: '向量检索', mistake_book: '错题库', rag_trace: '检索记录', runtime_config: '模型连接', exercise_bank: '习题库' };

function componentMessage(key: string, message = '') {
  if (key === 'runtime_config' && /LLM configuration is ready/i.test(message)) return '模型配置已就绪';
  return message;
}

function feedbackKind(message: string): AsyncStateKind {
  if (/失败|异常|错误|不可用/.test(message)) return 'error';
  if (/正在|检查中|下载中|安装中/.test(message)) return 'loading';
  if (/开发模式|不执行自动更新|无需更新|最新版本/.test(message)) return 'info';
  return 'success';
}
const SETTINGS_GROUPS: Array<{ label: string; items: Array<{ id: Tab; label: string }> }> = [
  { label: '常规', items: [{ id: 'appearance', label: '外观' }] },
  { label: '系统', items: [
    { id: 'health', label: '服务器健康' },
    { id: 'version', label: '版本更新' },
    { id: 'data', label: '备份恢复' },
  ] },
  { label: '模型', items: [
    { id: 'models', label: '模型配置' },
    { id: 'ingestion', label: '教材解析' },
  ] },
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

const SettingsPage: React.FC<{ standaloneTab?: 'subjects' }> = ({ standaloneTab }) => {
  const { bookName, setBookName, setSubject } = useChatContext();
  const { health, loading, loadHealth } = useSystemHealth(bookName);
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>(standaloneTab || 'health');
  const [version, setVersion] = useState<any>(null);
  const [subjects, setSubjects] = useState<SubjectNode[]>([]);
  const [books, setBooks] = useState<ManagedBook[]>([]);
  const [bookDrafts, setBookDrafts] = useState<Record<string, string>>({});
  const [envDraft, setEnvDraft] = useState<Record<string, string>>({});
  const [modelDraft, setModelDraft] = useState<ModelSettingsValue | null>(null);
  const [desktopUpdate, setDesktopUpdate] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [selectedSubjectIndex, setSelectedSubjectIndex] = useState(0);
  const [selectedChildIndex, setSelectedChildIndex] = useState<number | null>(null);
  const [reindexingBook, setReindexingBook] = useState('');

  const loadSettings = useCallback(async () => {
    const res = await get('/system/settings', 20000);
    if (!res?.success) return;
    setModelDraft(res.data.models || null);
    setSubjects(res.data.subjects || []);
    const env = res.data.env || {};
    setEnvDraft({
      MINERU_API_URL: env.MINERU_API_URL?.value || '',
      MINERU_CLI_COMMAND: env.MINERU_CLI_COMMAND?.value || '',
    });
  }, []);

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
    loadSettings().catch(() => setMessage('设置加载失败'));
    loadVersion().catch(() => undefined);
    loadBooks().catch(() => undefined);
  }, [loadSettings, loadVersion, loadBooks]);

  useEffect(() => {
    if (!window.kaoyanDesktop?.getUpdateStatus) return;
    let mounted = true;
    window.kaoyanDesktop.getUpdateStatus().then((status) => { if (mounted) setDesktopUpdate(status); }).catch(() => undefined);
    const unsubscribe = window.kaoyanDesktop.onUpdateStatus?.((status) => setDesktopUpdate(status));
    return () => {
      mounted = false;
      unsubscribe?.();
    };
  }, []);

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
  const activeBookCount = books.filter((book) => book.lifecycle_status !== 'archived').length;
  const persistentUpdateMessage = desktopUpdate && ['available', 'downloading', 'downloaded', 'installing', 'error'].includes(desktopUpdate.status)
    ? desktopUpdate.message
    : version?.message && feedbackKind(version.message) === 'error' ? version.message : '';


  const saveModels = async () => {
    setMessage('');
    if (!modelDraft) return;
    const res = await post('/system/settings/model-profiles', {
      activate: true,
      profile: { ...modelDraft, id: modelDraft.editing_profile_id, name: modelDraft.profile_name },
    }, 20000);
    setMessage(res?.message || (res?.success ? '已保存' : '保存失败'));
    if (res?.success) await loadSettings();
  };

  const saveIngestion = async () => {
    setMessage('');
    const res = await post('/system/settings/env', envDraft, 20000);
    setMessage(res?.message || (res?.success ? '教材解析配置已保存' : '保存失败'));
    if (res?.success) await loadSettings();
  };

  const activateModelProfile = async (profileId: string) => {
    setMessage('');
    const res = await post(`/system/settings/model-profiles/${encodeURIComponent(profileId)}/activate`, {}, 20000);
    setMessage(res?.message || (res?.success ? '模型方案已切换' : '切换失败'));
    if (res?.success) setModelDraft(res.data as ModelSettingsValue);
  };

  const deleteModelProfile = async (profileId: string) => {
    if (!window.confirm('删除这个模型方案吗？已保存的 API Key 不会被删除。')) return;
    const res = await del(`/system/settings/model-profiles/${encodeURIComponent(profileId)}`, 20000);
    setMessage(res?.message || (res?.success ? '模型方案已删除' : '删除失败'));
    if (res?.success) setModelDraft(res.data as ModelSettingsValue);
  };

  const testModelConnection = async (role: 'reasoning' | 'vision') => {
    if (!modelDraft) return { success: false, message: '模型配置尚未加载' };
    try {
      const res = await post('/system/settings/models/test', { role, settings: modelDraft }, 30000);
      return { success: Boolean(res?.success), message: res?.message || (res?.success ? '连接成功' : '连接失败') };
    } catch (error) {
      return { success: false, message: error instanceof Error ? error.message : '连接失败' };
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
    setMessage('已设为当前对话教材');
  };

  const openBookImport = () => {
    navigate('/books/import');
  };

  const reindexManagedBook = async (name: string) => {
    if (reindexingBook) return;
    setReindexingBook(name);
    setMessage(`正在重新索引《${name}》…`);
    try {
      const res = await post(`/books/${encodeURIComponent(name)}/reindex`, {}, 10 * 60 * 1000);
      setMessage(res?.message || (res?.success ? '教材索引已重建' : '重新索引失败'));
      if (res?.success) {
        await loadBooks();
        window.dispatchEvent(new Event('books:changed'));
      }
    } catch (error) {
      setMessage(error instanceof Error ? `重新索引失败：${error.message}` : '重新索引失败');
    } finally {
      setReindexingBook('');
    }
  };

  const reloadVectorStore = async () => {
    setMessage('正在重载向量库...');
    const res = await post('/system/vector-store/reload', {}, 90000);
    setMessage(res?.message || (res?.success ? '向量库已重载' : '向量库重载失败'));
    await loadHealth();
  };

  const updateApp = async () => {
    setMessage('');
    if (window.kaoyanDesktop?.checkForUpdates) {
      const res = await window.kaoyanDesktop.checkForUpdates();
      setDesktopUpdate(res);
      setMessage(res?.message || '更新检查完成');
      return;
    }
    const res = await post('/system/update', {}, 60000);
    setMessage(res?.message || '更新检查完成');
  };

  const downloadUpdate = async () => {
    setMessage('');
    const res = await window.kaoyanDesktop?.downloadUpdate?.();
    if (res) {
      setDesktopUpdate(res);
      setMessage(res.message || '开始下载更新');
    }
  };

  const installUpdate = async () => {
    setMessage('');
    const res = await window.kaoyanDesktop?.installUpdate?.();
    if (res) {
      setDesktopUpdate(res);
      setMessage(res.message || '正在安装更新');
    }
  };
  if (standaloneTab === 'subjects') {
    return (
      <div className="flex h-full min-w-0 flex-col bg-bg-primary">
        <header className="app-page-header border-b border-border bg-bg-primary">
          <div className="library-page-heading">
            <h2 className="app-page-title">教材库</h2>
            <span>{activeBookCount} 本活跃教材</span>
          </div>
          <div className="library-page-actions">
            <button onClick={openBookImport} className="app-secondary-button"><BookOpen className="h-4 w-4" />导入教材</button>
            <button onClick={() => saveSubjects()} className="app-primary-button"><Save className="h-4 w-4" />保存目录</button>
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
      <SettingsSidebar tab={tab} onTabChange={(nextTab) => { setMessage(''); setTab(nextTab); }} />
      <main className="settings-content-pane">
        {message && <div className="mb-5"><StatusBanner kind={feedbackKind(message)} title={message} /></div>}

        {tab === 'health' && (
          <section className="settings-page">
            <SettingsPageHeader title="服务器健康" description="查看 Texa 本地服务与数据组件的运行状态。" />
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
          </section>
        )}

        {tab === 'version' && (
          <section className="settings-page">
            <SettingsPageHeader title="版本更新" description="查看当前版本并检查 Texa 更新。" />
            <section className="settings-section" aria-labelledby="version-current-heading">
              <h4 id="version-current-heading" className="settings-section-title">当前版本</h4>
              <dl className="settings-definition-list">
                <div><dt>版本</dt><dd>{desktopUpdate?.currentVersion || version?.version || '未知'}</dd></div>
                <div><dt>分支</dt><dd>{version?.branch || '未知'}</dd></div>
                <div><dt>提交</dt><dd className="font-mono">{version?.commit || '未知'}</dd></div>
              </dl>
              {persistentUpdateMessage && <p className="settings-secondary">{persistentUpdateMessage}</p>}
              <p className="settings-secondary">本软件使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.</p>
              {desktopUpdate?.updateInfo?.version && <div className="status-success rounded-md border p-3 text-sm">可更新到 {desktopUpdate.updateInfo.version}</div>}
              {desktopUpdate?.status === 'downloading' && (
                <div>
                  <div className="mb-2 flex justify-between settings-secondary"><span>下载进度</span><span>{Math.round(desktopUpdate?.progress?.percent || 0)}%</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-bg-secondary"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(desktopUpdate?.progress?.percent || 0)}%` }} /></div>
                </div>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                <button onClick={loadVersion} className="app-secondary-button">读取版本</button>
                <button onClick={updateApp} disabled={desktopUpdate?.status === 'checking'} className="app-primary-button">{desktopUpdate?.status === 'checking' ? '检查中' : '检查更新'}</button>
                {desktopUpdate?.status === 'available' && <button onClick={downloadUpdate} className="app-secondary-button">下载更新</button>}
                {desktopUpdate?.status === 'downloaded' && <button onClick={installUpdate} className="app-secondary-button">重启安装</button>}
              </div>
            </section>
          </section>
        )}

        {tab === 'data' && <section className="settings-page"><SettingsPageHeader title="备份恢复" description="备份学习数据，并在需要时恢复。" /><DataSafety /></section>}

        {tab === 'appearance' && <section className="settings-page"><SettingsPageHeader title="外观" description="选择 Texa 的主题色与界面风格。" /><AppearanceSettings /></section>}

        {tab === 'models' && (
          <section className="settings-page">
            {modelDraft ? <ModelSettingsManager value={modelDraft} onChange={setModelDraft} onActivateProfile={activateModelProfile} onDeleteProfile={deleteModelProfile} onTestConnection={testModelConnection} /> : <PageState kind="loading" title="正在读取模型配置" />}
            <div className="settings-page-actions"><button onClick={saveModels} disabled={!modelDraft} className="app-primary-button"><Save className="h-4 w-4" />保存更改</button></div>
          </section>
        )}

        {tab === 'ingestion' && (
          <section className="settings-page">
            <SettingsPageHeader title="教材解析" description="配置教材导入时使用的 MinerU 文档解析服务。" />
            <section className="settings-section max-w-2xl" aria-labelledby="ingestion-service-heading">
              <h4 id="ingestion-service-heading" className="settings-section-title">解析服务</h4>
              <div className="space-y-5">
                <Field label="MinerU API URL"><input value={envDraft.MINERU_API_URL || ''} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_API_URL: e.target.value })} placeholder="http://127.0.0.1:9001" className="settings-input" /></Field>
                <Field label="本地 MinerU CLI（可选）"><input value={envDraft.MINERU_CLI_COMMAND || ''} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_CLI_COMMAND: e.target.value })} placeholder="mineru -p {input} -o {output}" className="settings-input" /></Field>
              </div>
            </section>
            <div className="settings-page-actions"><button onClick={saveIngestion} className="app-primary-button"><Save className="h-4 w-4" />保存更改</button></div>
          </section>
        )}
      </main>
    </div>
  );
};

const SettingsSidebar = ({ tab, onTabChange }: { tab: Tab; onTabChange: (tab: Tab) => void }) => (
  <aside className="settings-sidebar" aria-label="设置分类">
    <div className="settings-sidebar-groups">
      {SETTINGS_GROUPS.map((group) => (
        <section key={group.label} className="settings-nav-group" aria-labelledby={`settings-group-${group.label}`}>
          <h3 id={`settings-group-${group.label}`} className="settings-nav-group-label">{group.label}</h3>
          <div className="settings-nav-items">
            {group.items.map((item) => (
              <button key={item.id} onClick={() => onTabChange(item.id)} className={`settings-nav-item ${tab === item.id ? 'is-active' : ''}`} aria-current={tab === item.id ? 'page' : undefined}>{item.label}</button>
            ))}
          </div>
        </section>
      ))}
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
