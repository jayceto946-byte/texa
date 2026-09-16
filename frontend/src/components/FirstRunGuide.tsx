import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, BookOpen, CheckCircle2, KeyRound, Loader2, PackageOpen, ShieldCheck, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { del, get, post } from '../api/client';
import ModelSettingsManager from './settings/ModelSettingsManager';
import type { ModelRoleId, ModelSettingsValue } from './settings/ModelSettingsForm';

type AssetState = {
  id: string;
  label: string;
  installed: boolean;
  version_match: boolean;
  status: 'ready' | 'missing' | 'version_mismatch';
  repo_id?: string;
  revision?: string;
  version?: string;
  hf_endpoint?: string;
  url_configured?: boolean;
  path?: string;
};

type AssetStatus = {
  needs_setup: boolean;
  assets: {
    embedding_model: AssetState;
    vector_bundle: AssetState;
  };
};

type GuideBook = {
  name: string;
  display_name?: string;
  lifecycle_status?: string;
  readiness?: { technical?: { status?: string } };
};

const STORAGE_KEY = 'kaoyan:onboarding-complete:v2';
const FIRST_QUESTION_KEY = 'texa:onboarding-first-question';
const AWAITING_SOURCE_KEY = 'texa:onboarding-awaiting-source';
const steps = ['准备教材', '配置回答模型', '开始第一次学习'] as const;

const defaultEnvDraft = {
  MINERU_API_URL: '',
  MINERU_CLI_COMMAND: '',
};

export default function FirstRunGuide() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<AssetStatus | null>(null);
  const [books, setBooks] = useState<GuideBook[]>([]);
  const [envDraft, setEnvDraft] = useState<Record<string, string>>(defaultEnvDraft);
  const [modelDraft, setModelDraft] = useState<ModelSettingsValue | null>(null);
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState<string>('');
  const [message, setMessage] = useState('');
  const [privacyAcknowledged, setPrivacyAcknowledged] = useState(false);
  const [modelSaved, setModelSaved] = useState(false);

  const loadStatus = useCallback(async () => {
    if (window.localStorage.getItem(STORAGE_KEY) !== '1') setOpen(true);
    try {
      const [assetRes, settingsRes, booksRes] = await Promise.all([
        get('/system/assets/status', 20000),
        get('/system/settings', 20000),
        get('/books/list', 20000),
      ]);
      if (assetRes?.success) setStatus(assetRes.data as AssetStatus);
      if (settingsRes?.success) {
        const env = settingsRes.data?.env || {};
        setModelDraft(settingsRes.data?.models || null);
        setEnvDraft({
          ...defaultEnvDraft,
          MINERU_API_URL: env.MINERU_API_URL?.value || '',
          MINERU_CLI_COMMAND: env.MINERU_CLI_COMMAND?.value || '',
        });
      }
      if (booksRes?.success) setBooks((booksRes.data || []) as GuideBook[]);
    } catch {
      // The disclosure remains visible even while the backend is starting.
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    const onBooksChanged = () => {
      void loadStatus();
      setStep(0);
      setOpen(true);
    };
    const onSourcedAnswer = () => {
      window.localStorage.setItem(STORAGE_KEY, '1');
      window.localStorage.removeItem(AWAITING_SOURCE_KEY);
      setOpen(false);
    };
    window.addEventListener('books:changed', onBooksChanged);
    window.addEventListener('texa:onboarding-sourced-answer', onSourcedAnswer);
    return () => {
      window.removeEventListener('books:changed', onBooksChanged);
      window.removeEventListener('texa:onboarding-sourced-answer', onSourcedAnswer);
    };
  }, [loadStatus]);

  const startFirstQuestion = (question: string) => {
    if (!privacyAcknowledged) {
      setStep(2);
      setMessage('请先确认你已了解外部模型和 OCR 的数据传输范围。');
      return;
    }
    window.localStorage.setItem(FIRST_QUESTION_KEY, question);
    window.localStorage.setItem(AWAITING_SOURCE_KEY, '1');
    setOpen(false);
    navigate('/');
    window.dispatchEvent(new CustomEvent('texa:onboarding-question-selected', { detail: { question } }));
  };

  const dismiss = () => setOpen(false);

  const download = async (asset: 'embedding' | 'vector-bundle') => {
    setBusy(asset);
    setMessage(asset === 'embedding' ? '正在准备本地嵌入模型...' : '正在下载示例向量库...');
    try {
      const res = await post(`/system/assets/download/${asset}`, {}, asset === 'embedding' ? 20 * 60_000 : 10 * 60_000);
      setMessage(res?.message || (res?.success ? '下载完成' : '下载失败'));
      await loadStatus();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '下载失败');
    } finally {
      setBusy('');
    }
  };

  const saveApiKeys = async () => {
    setBusy('api-keys');
    setMessage('正在保存模型配置...');
    try {
      if (!modelDraft) throw new Error('模型配置尚未加载完成');
      const res = await post('/system/settings/model-profiles', {
        activate: true,
        profile: { ...modelDraft, id: modelDraft.editing_profile_id, name: modelDraft.profile_name },
      }, 20000);
      if (res?.success && Object.values(envDraft).some((value) => value.trim())) {
        await post('/system/settings/env', envDraft, 20000);
      }
      setMessage(res?.message || (res?.success ? '配置已保存' : '保存失败'));
      if (res?.success) setModelSaved(true);
      await loadStatus();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '保存失败');
    } finally {
      setBusy('');
    }
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

  const testModelConnection = async (role: ModelRoleId) => {
    if (!modelDraft) return { success: false, message: '模型配置尚未加载' };
    try {
      const res = await post('/system/settings/models/test', { role, settings: modelDraft }, 30000);
      return { success: Boolean(res?.success), message: res?.message || (res?.success ? '连接成功' : '连接失败') };
    } catch (error) {
      return { success: false, message: error instanceof Error ? error.message : '连接失败' };
    }
  };

  if (!open) return null;

  const embedding = status?.assets.embedding_model;
  const hasPrimaryKey = Boolean(modelDraft && (modelDraft.credentials.reasoning.configured || !modelDraft.credentials.reasoning.required));
  const activeBooks = books.filter((book) => book.lifecycle_status !== 'archived');
  const readyBooks = activeBooks.filter((book) => book.readiness?.technical?.status === 'ready');
  const hasLearningMaterial = readyBooks.length > 0;
  const firstBook = readyBooks[0] || activeBooks[0];

  return (
    <div className="app-overlay-enter fixed inset-0 z-[1300] flex items-center justify-center bg-[#1f2824]/45 p-4">
      <section className="app-large-dialog-enter flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-[var(--radius-large)] border border-border bg-bg-primary shadow-lg">
        <header className="flex items-center justify-between border-b border-border bg-bg-card px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <PackageOpen className="h-5 w-5 text-accent" />
            <div>
              <h2 className="text-base font-semibold text-text-primary">首次打开 Texa</h2>

            </div>
          </div>
          <button type="button" onClick={dismiss} className="rounded-lg p-1.5 text-text-secondary hover:bg-bg-secondary hover:text-text-primary" aria-label="关闭，稍后再次提示">
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-[180px_minmax(0,1fr)]">
          <aside className="border-r border-border bg-bg-secondary/80 p-3">
            {steps.map((item, index) => (
              <button
                key={item}
                type="button"
                onClick={() => setStep(index)}
                className={`mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${step === index ? 'bg-[var(--accent-soft)] text-accent' : 'text-text-secondary hover:bg-bg-card hover:text-text-primary'}`}
              >
                <span className="w-4 text-[11px] tabular-nums">{index + 1}</span>
                {item}
              </button>
            ))}
          </aside>

          <main className="min-h-0 overflow-y-auto p-5">
            {message && <div className="mb-4 rounded-lg border border-border bg-bg-secondary px-4 py-2 text-sm text-text-primary">{message}</div>}

            {step === 0 && (
              <section className="space-y-4">
                <div className="border-y border-border py-5">
                  <div className="flex items-center gap-2 text-sm font-semibold text-text-primary"><BookOpen className="h-5 w-5 text-accent" />先准备一本要学习的教材</div>
                  <p className="mt-2 text-sm leading-6 text-text-secondary">Texa 会从教材中查找依据，并在回答旁提供可查看的来源。</p>
                  {hasLearningMaterial ? (
                    <div className="mt-4 flex items-start gap-2 border-l-2 border-[var(--success)] pl-3 text-sm text-text-primary"><CheckCircle2 className="mt-0.5 h-4 w-4 text-[var(--success)]" /><span><strong>{firstBook?.display_name || firstBook?.name}</strong> 已可用于学习。{readyBooks.length > 1 ? `另有 ${readyBooks.length - 1} 本教材可用。` : ''}</span></div>
                  ) : activeBooks.length ? (
                    <div className="mt-4 border-l-2 border-[var(--warning)] pl-3 text-sm leading-6 text-text-secondary">教材已添加，但还在准备中。完成后即可进入下一步；你也可以打开教材页查看状态。</div>
                  ) : (
                    <div className="mt-4 border-l-2 border-border pl-3 text-sm leading-6 text-text-secondary">尚未添加教材。导入 PDF、Word 或已解析的教材内容后，回到这里继续。</div>
                  )}
                </div>
                <button type="button" onClick={() => { setOpen(false); navigate('/books/import'); }} className="app-primary-button"><BookOpen className="h-4 w-4" />{activeBooks.length ? '查看教材状态' : '导入第一本教材'}</button>
              </section>
            )}

            {step === 1 && (
              <section className="space-y-4">
                {!embedding?.installed && <div className="border-l-2 border-[var(--warning)] pl-3 text-sm leading-6 text-text-secondary">教材检索所需的本地资源尚未准备。<button type="button" onClick={() => download('embedding')} disabled={busy === 'embedding'} className="ml-2 text-accent hover:underline">{busy === 'embedding' ? '准备中…' : '立即准备'}</button></div>}
                {modelDraft && <ModelSettingsManager guided value={modelDraft} onChange={setModelDraft} onActivateProfile={activateModelProfile} onDeleteProfile={deleteModelProfile} onTestConnection={testModelConnection} />}
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
                  <span className={`inline-flex items-center gap-1 text-xs ${hasPrimaryKey || modelSaved ? 'text-[var(--success)]' : 'text-[var(--warning-text)]'}`}><ShieldCheck className="h-3.5 w-3.5" />{hasPrimaryKey || modelSaved ? '回答模型已可用' : '请填写模型所需凭证'}</span>
                  <button type="button" onClick={saveApiKeys} disabled={busy === 'api-keys'} className="app-primary-button">{busy === 'api-keys' ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}保存并继续</button>
                </div>
              </section>
            )}

            {step === 2 && (
              <section className="space-y-4">
                <div className="border-y border-border py-5">
                  <h3 className="text-sm font-semibold text-text-primary">用一个有来源的问题开始</h3>
                  <p className="mt-2 text-sm leading-6 text-text-secondary">选择下面的问题后，它会填入学习区。发送并获得带来源的回答后，首次使用才算完成。</p>
                </div>
                <div className="divide-y divide-border border-y border-border">
                  {['请概括当前教材这一章的核心内容，并标注来源。', '根据当前教材，解释一个最重要的概念并给出出处。', '我应该从当前教材的哪一部分开始复习？请说明依据。'].map((question) => <button key={question} type="button" onClick={() => startFirstQuestion(question)} className="flex w-full items-center justify-between gap-4 py-3 text-left text-sm text-text-primary hover:text-accent"><span>{question}</span><ArrowRight className="h-4 w-4 shrink-0" /></button>)}
                </div>
                <label className="flex items-start gap-2 text-xs leading-5 text-text-secondary"><input type="checkbox" checked={privacyAcknowledged} onChange={(event) => setPrivacyAcknowledged(event.target.checked)} className="mt-1" /><span>我了解：问题和必要教材片段会发送给已配置的回答服务；图片仅在我主动使用图片功能时发送。</span></label>
              </section>
            )}
          </main>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-bg-card px-5 py-4">
          <button type="button" onClick={dismiss} className="rounded-lg border border-border px-3 py-2 text-sm text-text-secondary hover:border-accent hover:text-text-primary">稍后再看</button>
          <div className="flex gap-2">
            <button type="button" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0} className="rounded-lg border border-border px-3 py-2 text-sm text-text-primary hover:border-accent disabled:opacity-40">上一步</button>
            {step < steps.length - 1 ? (
              <button type="button" onClick={() => setStep(step + 1)} disabled={(step === 0 && !hasLearningMaterial) || (step === 1 && !(hasPrimaryKey || modelSaved))} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45">下一步</button>
            ) : (
              <span className="text-xs text-text-secondary">请选择一个首问继续</span>
            )}
          </div>
        </footer>
      </section>
    </div>
  );
}
