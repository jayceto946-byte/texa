import { useCallback, useEffect, useState } from 'react';
import type React from 'react';
import { BookOpen, CheckCircle2, Database, Download, KeyRound, Loader2, PackageOpen, ShieldCheck, X } from 'lucide-react';
import { get, post } from '../api/client';

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

type EnvStatus = Record<string, { configured: boolean; value: string }>;

const STORAGE_KEY = 'kaoyan:onboarding-complete:v2';
const steps = ['快速了解', '本地资源', '模型配置'] as const;

const defaultEnvDraft = {
  LLM_BACKEND: 'deepseek',
  DEEPSEEK_API_BASE: 'https://api.deepseek.com/v1',
  DEEPSEEK_MODEL_NAME: 'deepseek-v4-pro',
  DEEPSEEK_API_KEY: '',
  MOONSHOT_API_BASE: 'https://api.moonshot.cn/v1',
  MOONSHOT_API_KEY: '',
  KIMI_VISION_MODEL: 'kimi-k2.5',
  OPENAI_API_BASE: 'https://api.openai.com/v1',
  OPENAI_API_KEY: '',
  LLM_MODEL_NAME: '',
  MINERU_API_URL: '',
  MINERU_CLI_COMMAND: '',
};

export default function FirstRunGuide() {
  const [status, setStatus] = useState<AssetStatus | null>(null);
  const [envStatus, setEnvStatus] = useState<EnvStatus>({});
  const [envDraft, setEnvDraft] = useState<Record<string, string>>(defaultEnvDraft);
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState<string>('');
  const [message, setMessage] = useState('');
  const [privacyAcknowledged, setPrivacyAcknowledged] = useState(false);

  const loadStatus = useCallback(async () => {
    if (window.localStorage.getItem(STORAGE_KEY) !== '1') setOpen(true);
    try {
      const [assetRes, settingsRes] = await Promise.all([
        get('/system/assets/status', 20000),
        get('/system/settings', 20000),
      ]);
      if (assetRes?.success) setStatus(assetRes.data as AssetStatus);
      if (settingsRes?.success) {
        const env = settingsRes.data?.env || {};
        setEnvStatus(env);
        setEnvDraft({
          ...defaultEnvDraft,
          LLM_BACKEND: env.LLM_BACKEND?.value || defaultEnvDraft.LLM_BACKEND,
          DEEPSEEK_API_BASE: env.DEEPSEEK_API_BASE?.value || defaultEnvDraft.DEEPSEEK_API_BASE,
          DEEPSEEK_MODEL_NAME: env.DEEPSEEK_MODEL_NAME?.value || defaultEnvDraft.DEEPSEEK_MODEL_NAME,
          MOONSHOT_API_BASE: env.MOONSHOT_API_BASE?.value || defaultEnvDraft.MOONSHOT_API_BASE,
          KIMI_VISION_MODEL: env.KIMI_VISION_MODEL?.value || defaultEnvDraft.KIMI_VISION_MODEL,
          OPENAI_API_BASE: env.OPENAI_API_BASE?.value || defaultEnvDraft.OPENAI_API_BASE,
          LLM_MODEL_NAME: env.LLM_MODEL_NAME?.value || '',
          MINERU_API_URL: env.MINERU_API_URL?.value || '',
          MINERU_CLI_COMMAND: env.MINERU_CLI_COMMAND?.value || '',
          DEEPSEEK_API_KEY: '',
          MOONSHOT_API_KEY: '',
          OPENAI_API_KEY: '',
        });
      }
    } catch {
      // The disclosure remains visible even while the backend is starting.
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const finish = () => {
    if (!privacyAcknowledged) {
      setStep(0);
      setMessage('请先确认你已了解外部模型和 OCR 的数据传输范围。');
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, '1');
    setOpen(false);
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
      const payload: Record<string, string> = {};
      for (const [key, value] of Object.entries(envDraft)) {
        if ((key.endsWith('_API_KEY') || key === 'OPENAI_API_KEY') && !value.trim()) continue;
        payload[key] = value.trim();
      }
      const res = await post('/system/settings/env', payload, 20000);
      setMessage(res?.message || (res?.success ? '配置已保存' : '保存失败'));
      await loadStatus();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '保存失败');
    } finally {
      setBusy('');
    }
  };

  if (!open) return null;

  const embedding = status?.assets.embedding_model;
  const vector = status?.assets.vector_bundle;
  const hasPrimaryKey = Boolean(envStatus.DEEPSEEK_API_KEY?.configured || envStatus.MOONSHOT_API_KEY?.configured || envStatus.OPENAI_API_KEY?.configured);

  return (
    <div className="app-overlay-enter fixed inset-0 z-[1300] flex items-center justify-center bg-[#1f2824]/45 p-4">
      <section className="app-large-dialog-enter flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-[var(--radius-large)] border border-border bg-bg-primary shadow-lg">
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
                <div className="border-y border-border py-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary"><BookOpen className="h-5 w-5 text-accent" />你会用到的几个入口</div>
                  <div className="divide-y divide-border">
                    <GuidePoint title="对话" text="围绕教材、错题和知识点提问，系统会优先走本地教材检索。" />
                    <GuidePoint title="教材库" text="管理教材与学科范围；导入后会建立章节和本地检索索引。" />
                    <GuidePoint title="错题本" text="保存错题、错因和复习状态，后续按概念和来源回看。" />
                    <GuidePoint title="设置" text="侧栏底部可检查服务、版本、备份和模型配置。" />
                  </div>
                </div>
                <div className="border-l-2 border-accent/50 pl-4 text-sm leading-6 text-text-secondary">
                  本地嵌入模型只在本机完成教材语义检索。问答时，当前问题、必要会话上下文和选中的教材证据会发送给你配置的 LLM 服务；使用 Kimi 图片 OCR 时，所选图片会发送给 Moonshot。外部服务将按各自隐私政策处理数据并可能产生费用。
                </div>
                <label className="flex items-start gap-2 border-t border-border pt-4 text-sm leading-6 text-text-primary">
                  <input type="checkbox" checked={privacyAcknowledged} onChange={(event) => setPrivacyAcknowledged(event.target.checked)} className="mt-1" />
                  <span>我已了解上述数据传输范围，并会避免上传无权处理或包含敏感个人信息的内容。</span>
                </label>
              </section>
            )}

            {step === 1 && (
              <section className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <AssetPanel
                    icon={<Download className="h-5 w-5" />}
                    title="本地嵌入模型"
                    subtitle={`${embedding?.repo_id || 'BAAI/bge-small-zh-v1.5'} / ${embedding?.revision || 'main'}`}
                    detail={`默认镜像：${embedding?.hf_endpoint || 'https://hf-mirror.com'}`}
                    ready={embedding?.status === 'ready'}
                    busy={busy === 'embedding'}
                    actionLabel="准备模型"
                    onAction={() => download('embedding')}
                  />
                  <AssetPanel
                    icon={<Database className="h-5 w-5" />}
                    title="示例向量库"
                    subtitle={`版本：${vector?.version || 'demo-v1'}`}
                    detail={vector?.url_configured ? '已配置下载地址' : '尚未配置下载地址，可跳过'}
                    ready={vector?.status === 'ready'}
                    busy={busy === 'vector-bundle'}
                    actionLabel="下载示例数据"
                    disabled={!vector?.url_configured}
                    onAction={() => download('vector-bundle')}
                  />
                </div>
                <div className="border-t border-border pt-4 text-sm leading-6 text-text-secondary">
                  模型和向量库会保存到用户数据目录，软件更新不会覆盖你的教材、错题和个人索引。
                </div>
              </section>
            )}

            {step === 2 && (
              <section className="space-y-4">
                <div className="border-l-2 border-accent/50 pl-4 text-sm leading-6 text-text-secondary">
                  API Key 只写入本机 .env。后端状态接口只返回“是否已配置”，不会把已有密钥回显到前端。
                </div>
                <div className="border-t border-border pt-4 text-sm leading-6 text-text-secondary">
                  Recommended OCR path: run MinerU 3.x on a rented GPU or external service, then import the output zip. Local MinerU CLI is optional and should live in a separate Python 3.10 environment with MinerU/Paddle/CUDA dependencies.
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="推理后端">
                    <select value={envDraft.LLM_BACKEND} onChange={(e) => setEnvDraft({ ...envDraft, LLM_BACKEND: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm">
                      <option value="deepseek">DeepSeek</option>
                      <option value="moonshot">Moonshot/Kimi</option>
                      <option value="openai">OpenAI</option>
                      <option value="ollama">Ollama</option>
                    </select>
                  </Field>
                  <Field label="DeepSeek 模型"><input value={envDraft.DEEPSEEK_MODEL_NAME} onChange={(e) => setEnvDraft({ ...envDraft, DEEPSEEK_MODEL_NAME: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
                  <Field label={`DeepSeek API Key（${envStatus.DEEPSEEK_API_KEY?.configured ? '已配置' : '未配置'}）`}><input type="password" autoComplete="off" value={envDraft.DEEPSEEK_API_KEY} onChange={(e) => setEnvDraft({ ...envDraft, DEEPSEEK_API_KEY: e.target.value })} placeholder="留空则不修改" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
                  <Field label="DeepSeek Base URL"><input value={envDraft.DEEPSEEK_API_BASE} onChange={(e) => setEnvDraft({ ...envDraft, DEEPSEEK_API_BASE: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
                  <Field label={`Kimi/OCR API Key（${envStatus.MOONSHOT_API_KEY?.configured ? '已配置' : '未配置'}）`}><input type="password" autoComplete="off" value={envDraft.MOONSHOT_API_KEY} onChange={(e) => setEnvDraft({ ...envDraft, MOONSHOT_API_KEY: e.target.value })} placeholder="留空则不修改" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
                  <Field label="Kimi/OCR 模型"><input value={envDraft.KIMI_VISION_MODEL} onChange={(e) => setEnvDraft({ ...envDraft, KIMI_VISION_MODEL: e.target.value })} className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
                  <Field label="MinerU API URL (recommended external service)"><input value={envDraft.MINERU_API_URL} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_API_URL: e.target.value })} placeholder="SSH tunnel example: http://127.0.0.1:9001" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
                  <Field label="Local MinerU CLI (advanced, optional)"><input value={envDraft.MINERU_CLI_COMMAND} onChange={(e) => setEnvDraft({ ...envDraft, MINERU_CLI_COMMAND: e.target.value })} placeholder="Example: mineru -p {input} -o {output}" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm" /></Field>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs ${hasPrimaryKey ? 'bg-[#edf6f0] text-[var(--success)]' : 'bg-[#fff7de] text-[var(--warning)]'}`}>
                    <ShieldCheck className="h-3.5 w-3.5" />{hasPrimaryKey ? '已有可用 Key' : '尚未配置 Key'}
                  </span>
                  <button type="button" onClick={saveApiKeys} disabled={busy === 'api-keys'} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60">
                    {busy === 'api-keys' ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                    保存配置
                  </button>
                </div>
              </section>
            )}
          </main>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-bg-card px-5 py-4">
          <button type="button" onClick={dismiss} className="rounded-lg border border-border px-3 py-2 text-sm text-text-secondary hover:border-accent hover:text-text-primary">稍后再看</button>
          <div className="flex gap-2">
            <button type="button" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0} className="rounded-lg border border-border px-3 py-2 text-sm text-text-primary hover:border-accent disabled:opacity-40">上一步</button>
            {step < steps.length - 1 ? (
              <button type="button" onClick={() => setStep(step + 1)} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover">下一步</button>
            ) : (
              <button type="button" onClick={finish} disabled={!privacyAcknowledged} className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50">我已了解并开始使用</button>
            )}
          </div>
        </footer>
      </section>
    </div>
  );
}

function GuidePoint({ title, text }: { title: string; text: string }) {
  return <div className="grid gap-1 py-2.5 sm:grid-cols-[88px_minmax(0,1fr)]"><div className="text-sm font-medium text-text-primary">{title}</div><div className="text-xs leading-5 text-text-secondary">{text}</div></div>;
}

function AssetPanel({
  icon,
  title,
  subtitle,
  detail,
  ready,
  busy,
  disabled,
  actionLabel,
  onAction,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  detail: string;
  ready: boolean;
  busy: boolean;
  disabled?: boolean;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="rounded-[var(--radius-medium)] border border-border bg-bg-card p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary"><span className="text-accent">{icon}</span>{title}</div>
      <div className="text-xs leading-5 text-text-secondary">{subtitle}</div>
      <div className="mt-1 text-xs leading-5 text-text-secondary">{detail}</div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs ${ready ? 'bg-[#edf6f0] text-[var(--success)]' : 'bg-[#fff7de] text-[var(--warning)]'}`}>
          {ready ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Database className="h-3.5 w-3.5" />}{ready ? '已就绪' : '待准备'}
        </span>
        <button type="button" onClick={onAction} disabled={ready || busy || disabled} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-text-primary hover:border-accent disabled:cursor-not-allowed disabled:opacity-50">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}{ready ? '完成' : actionLabel}
        </button>
      </div>
    </div>
  );
}

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="block space-y-1.5 text-sm text-text-primary"><span className="text-xs font-medium text-text-secondary">{label}</span>{children}</label>
);
