import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, CircleX, RefreshCw, Save } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { del, get, patch, post } from '../api/client';
import { useSystemHealth } from '../hooks/useSystemHealth';
import { useChatContext } from '../contexts/ChatContext';
import type { SystemHealthStatus } from '../types';
import LibraryManager from './settings/LibraryManager';
import DataSafety from './settings/DataSafety';
import { PageState, StatusBanner } from './ui/AsyncState';

type SubjectNode = { name: string; children: string[] };
type ManagedBook = { name: string; book_id?: string; storage_name?: string; display_name?: string; lifecycle_status?: 'active' | 'archived'; subject?: string; path?: string; has_pdf?: boolean; chapter_count?: number; size?: number; book_role?: 'standalone' | 'core' | 'reference'; rag_priority?: number; resource_group?: string };
type Tab = 'health' | 'version' | 'data' | 'subjects' | 'models';

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
const secretKeys = ['DEEPSEEK_API_KEY', 'MOONSHOT_API_KEY', 'OPENAI_API_KEY'];
const SETTINGS_TABS: Array<{ id: Tab; label: string }> = [
  { id: 'health', label: '服务器健康' },
  { id: 'version', label: '版本更新' },
  { id: 'data', label: '备份恢复' },
  { id: 'models', label: '模型配置' },
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
  const [settings, setSettings] = useState<any>(null);
  const [subjects, setSubjects] = useState<SubjectNode[]>([]);
  const [books, setBooks] = useState<ManagedBook[]>([]);
  const [bookDrafts, setBookDrafts] = useState<Record<string, string>>({});
  const [envDraft, setEnvDraft] = useState<Record<string, string>>({});
  const [desktopUpdate, setDesktopUpdate] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [selectedSubjectIndex, setSelectedSubjectIndex] = useState(0);
  const [selectedChildIndex, setSelectedChildIndex] = useState<number | null>(null);

  const loadSettings = useCallback(async () => {
    const res = await get('/system/settings', 20000);
    if (!res?.success) return;
    setSettings(res.data);
    setSubjects(res.data.subjects || []);
    const env = res.data.env || {};
    setEnvDraft({
      LLM_BACKEND: env.LLM_BACKEND?.value || 'deepseek',
      DEEPSEEK_API_BASE: env.DEEPSEEK_API_BASE?.value || 'https://api.deepseek.com/v1',
      DEEPSEEK_MODEL_NAME: env.DEEPSEEK_MODEL_NAME?.value || 'deepseek-v4-pro',
      MOONSHOT_API_BASE: env.MOONSHOT_API_BASE?.value || 'https://api.moonshot.cn/v1',
      KIMI_VISION_MODEL: env.KIMI_VISION_MODEL?.value || 'kimi-k2.5',
      OPENAI_API_BASE: env.OPENAI_API_BASE?.value || 'https://api.openai.com/v1',
      LLM_MODEL_NAME: env.LLM_MODEL_NAME?.value || '',
      MINERU_API_URL: env.MINERU_API_URL?.value || '',
      MINERU_CLI_COMMAND: env.MINERU_CLI_COMMAND?.value || '',
      DEEPSEEK_API_KEY: '',
      MOONSHOT_API_KEY: '',
      OPENAI_API_KEY: '',
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


  const saveEnv = async () => {
    setMessage('');
    const payload: Record<string, string> = {};
    for (const [key, value] of Object.entries(envDraft)) {
      if (secretKeys.includes(key) && !value.trim()) continue;
      payload[key] = value;
    }
    const res = await post('/system/settings/env', payload, 20000);
    setMessage(res?.message || (res?.success ? '已保存' : '保存失败'));
    if (res?.success) await loadSettings();
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
        <header className="app-page-header border-b border-border bg-bg-card">
          <div>
            <h2 className="app-page-title">教材库</h2>
            <p className="type-caption mt-0.5 text-text-secondary">组织学科、切换当前教材并管理检索范围</p>
          </div>
          <div className="window-drag-region" aria-hidden="true" />
        </header>
        <main className="mx-auto min-h-0 w-full max-w-6xl flex-1 overflow-y-auto p-4 sm:p-5">
          {message && <div className="mb-4"><StatusBanner kind={message.includes('失败') || message.includes('异常') ? 'error' : message.includes('正在') ? 'loading' : 'success'} title={message} /></div>}
          <LibraryManager
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
            onSaveSubjects={() => saveSubjects()}
            onImportBook={openBookImport}
            onRefresh={loadBooks}
            onMoveBook={moveBookToTarget}
            onSwitchBook={switchManagedBook}
            onArchiveBook={deleteManagedBook}
            onRestoreBook={restoreManagedBook}
            onRenameBook={renameManagedBook}
            onSetRole={setBookRole}
            onSetResourceGroup={setBookResourceGroup}
            currentBookName={bookName}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-bg-primary">
      <header className="app-page-header border-b border-border bg-bg-card">
        <h2 className="app-page-title">设置</h2>
        <div className="window-drag-region" aria-hidden="true" />
      </header>
      <div className="mx-auto grid min-h-0 w-full max-w-5xl flex-1 grid-cols-1 md:grid-cols-[168px_minmax(0,1fr)]">
        <SettingsSidebar tab={tab} onTabChange={setTab} />
  <main className="min-h-0 overflow-y-auto p-5">
    {message && <div className="mb-4"><StatusBanner kind={message.includes('失败') || message.includes('异常') ? 'error' : message.includes('正在') ? 'loading' : 'success'} title={message} /></div>}

    {tab === 'health' && (
      <section className="space-y-4">
        {loading && !health && <PageState kind="loading" title="正在检查系统状态" />}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-medium text-text-primary"><StatusIcon className={`h-4 w-4 ${meta.iconClass}`} />{meta.label}</div>
          <button onClick={loadHealth} className="app-secondary-button min-h-8 px-3 text-xs"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />重新检查</button>
        </div>
        <div className="app-panel divide-y divide-border overflow-hidden">
          {health && Object.entries(health.components).map(([key, item]) => {
            const itemMeta = statusMeta[item.status] || statusMeta.degraded;
            const ItemIcon = itemMeta.icon;
            return (
              <div key={key} className="flex items-start gap-3 px-4 py-3.5">
                <ItemIcon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${itemMeta.iconClass}`} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-text-primary">{componentLabels[key] || '系统组件'}</div>
                  <div className="mt-0.5 text-xs leading-5 text-text-secondary">{componentMessage(key, item.message)}</div>
                </div>
                {key === 'vector_store' && (
                  <button type="button" onClick={reloadVectorStore} className="app-secondary-button min-h-8 flex-shrink-0 px-3 text-xs"><RefreshCw className="h-3.5 w-3.5" />重载</button>
                )}
              </div>
            );
          })}
        </div>
      </section>
    )}

    {tab === 'version' && (
      <section className="space-y-4">
        <div className="rounded-xl border border-border bg-bg-card p-4 text-sm text-text-primary">
          <div>当前版本：{desktopUpdate?.currentVersion || version?.version || '未知'}</div>
          <div className="mt-2 text-text-secondary">分支：{version?.branch || '未知'} / 提交：{version?.commit || '未知'}</div>
          <div className="mt-2 text-xs text-text-secondary">{desktopUpdate?.message || version?.message || '正在读取版本信息...'}</div>
        </div>
        {desktopUpdate?.updateInfo?.version && <div className="rounded-xl border border-[#bfd4c6] bg-[#edf6f0] p-4 text-sm text-[var(--success)]">可更新到：{desktopUpdate.updateInfo.version}</div>}
        {desktopUpdate?.status === 'downloading' && (
          <div className="rounded-xl border border-border bg-bg-card p-4">
            <div className="mb-2 flex justify-between text-xs text-text-secondary"><span>下载进度</span><span>{Math.round(desktopUpdate?.progress?.percent || 0)}%</span></div>
            <div className="h-2 overflow-hidden rounded-full bg-bg-secondary"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(desktopUpdate?.progress?.percent || 0)}%` }} /></div>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button onClick={loadVersion} className="rounded-lg border border-border px-3 py-2 text-sm hover:border-accent">读取版本</button>
          <button onClick={updateApp} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover">检查更新</button>
          {desktopUpdate?.status === 'available' && <button onClick={downloadUpdate} className="rounded-lg border border-border px-3 py-2 text-sm hover:border-accent">下载更新</button>}
          {desktopUpdate?.status === 'downloaded' && <button onClick={installUpdate} className="rounded-lg border border-border px-3 py-2 text-sm hover:border-accent">重启安装</button>}
        </div>
      </section>
    )}

    {tab === 'data' && (
      <DataSafety />
    )}

    {tab === 'models' && (
      <section className="space-y-4">
        <div className="rounded-lg border border-border bg-bg-card p-3 text-xs leading-5 text-text-secondary">API Key 只写入本地 .env；界面只显示是否已配置，不回显密钥。保存后新请求会读取新配置，已有长任务可能需要重启后端。</div>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="推理后端"><select value={envDraft.LLM_BACKEND || 'deepseek'} onChange={(e) => setEnvDraft({ ...envDraft, LLM_BACKEND: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm"><option value="deepseek">DeepSeek</option><option value="moonshot">Moonshot/Kimi</option><option value="openai">OpenAI</option><option value="ollama">Ollama</option></select></Field>
          <Field label="DeepSeek 模型"><input value={envDraft.DEEPSEEK_MODEL_NAME || ''} onChange={(e) => setEnvDraft({ ...envDraft, DEEPSEEK_MODEL_NAME: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label={`DeepSeek API Key（${settings?.env?.DEEPSEEK_API_KEY?.configured ? '已配置' : '未配置'}）`}><input type="password" value={envDraft.DEEPSEEK_API_KEY || ''} onChange={(e) => setEnvDraft({ ...envDraft, DEEPSEEK_API_KEY: e.target.value })} placeholder="留空则不修改" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label="DeepSeek Base URL"><input value={envDraft.DEEPSEEK_API_BASE || ''} onChange={(e) => setEnvDraft({ ...envDraft, DEEPSEEK_API_BASE: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label={`OCR/Kimi API Key（${settings?.env?.MOONSHOT_API_KEY?.configured ? '已配置' : '未配置'}）`}><input type="password" value={envDraft.MOONSHOT_API_KEY || ''} onChange={(e) => setEnvDraft({ ...envDraft, MOONSHOT_API_KEY: e.target.value })} placeholder="留空则不修改" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label="OCR/Kimi 模型"><input value={envDraft.KIMI_VISION_MODEL || ''} onChange={(e) => setEnvDraft({ ...envDraft, KIMI_VISION_MODEL: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label="MinerU API URL（推荐外部服务）"><input value={envDraft.MINERU_API_URL || ''} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_API_URL: e.target.value })} placeholder="SSH 隧道示例：http://127.0.0.1:9001" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label="本地 MinerU CLI（高级，可选）"><input value={envDraft.MINERU_CLI_COMMAND || ''} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_CLI_COMMAND: e.target.value })} placeholder="Example: mineru -p {input} -o {output}" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label={`OpenAI API Key（${settings?.env?.OPENAI_API_KEY?.configured ? '已配置' : '未配置'}）`}><input type="password" value={envDraft.OPENAI_API_KEY || ''} onChange={(e) => setEnvDraft({ ...envDraft, OPENAI_API_KEY: e.target.value })} placeholder="留空则不修改" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
          <Field label="通用模型名"><input value={envDraft.LLM_MODEL_NAME || ''} onChange={(e) => setEnvDraft({ ...envDraft, LLM_MODEL_NAME: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
        </div>
        <button onClick={saveEnv} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover"><Save className="h-4 w-4" />保存模型配置</button>
      </section>
    )}
        </main>
      </div>
    </div>
  );
};

const SettingsSidebar = ({ tab, onTabChange }: { tab: Tab; onTabChange: (tab: Tab) => void }) => (
  <aside className="overflow-x-auto border-b border-border bg-bg-secondary/80 p-3 md:border-b-0 md:border-r">
    <div className="flex min-w-max gap-1 md:block md:min-w-0">
      {SETTINGS_TABS.map((item) => (
        <button key={item.id} onClick={() => onTabChange(item.id)} className={`w-auto whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm md:mb-1 md:w-full ${tab === item.id ? 'bg-[var(--accent-soft)] text-accent' : 'text-text-secondary hover:bg-bg-card hover:text-text-primary'}`}>
          {item.label}
        </button>
      ))}
    </div>
  </aside>
);

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="block space-y-1.5 text-sm text-text-primary"><span className="text-xs font-medium text-text-secondary">{label}</span>{children}</label>
);

export default SettingsPage;
