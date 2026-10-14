import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Check, Loader2 } from 'lucide-react';
import { get, post, del, isRemoteBrowser } from '../api/client';
import ModelSettingsManager from './settings/ModelSettingsManager';
import type { ModelRoleId, ModelSettingsValue } from './settings/ModelSettingsForm';
import './Welcome.css';

const KEY = 'texa:setup-complete:v3';
const configured = (value: ModelSettingsValue | null) => Boolean(value?.roles.reasoning.model &&
  (!value.credentials.reasoning.required || value.credentials.reasoning.configured));
type Step = 0 | 1 | 2;
type Phase = 'idle' | 'exit' | 'enter';

export default function FirstRunGuide({ children }: { children: ReactNode }) {
  const [complete, setComplete] = useState(false);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState<Step>(0);
  const [phase, setPhase] = useState<Phase>('idle');
  const [direction, setDirection] = useState<'forward' | 'reverse'>('forward');
  const [draft, setDraft] = useState<ModelSettingsValue | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mainRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const transitionLock = useRef(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const navigate = (next: Step) => {
    if (transitionLock.current || next === step) return;
    transitionLock.current = true;
    const reverse = next < step;
    setDirection(reverse ? 'reverse' : 'forward');
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setStep(next);
      mainRef.current?.scrollTo(0, 0);
      requestAnimationFrame(() => { headingRef.current?.focus(); transitionLock.current = false; });
      return;
    }
    setPhase('exit');
    timers.current.push(setTimeout(() => {
      setStep(next);
      mainRef.current?.scrollTo(0, 0);
      setPhase('enter');
      timers.current.push(setTimeout(() => {
        setPhase('idle');
        headingRef.current?.focus();
        transitionLock.current = false;
      }, 220));
    }, 140));
  };

  const load = async () => {
    if (isRemoteBrowser()) { setComplete(true); setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const response = await get('/system/settings', 20000);
      if (!response.success || !response.data?.models) throw new Error('暂时无法读取模型配置');
      const models = response.data.models as ModelSettingsValue;
      setDraft(models); setSaved(configured(models));
      // The completion flag never contains credentials.
      const legacyComplete = localStorage.getItem(KEY) === '1' || localStorage.getItem('kaoyan:onboarding-complete:v2') === '1';
      const desktop = window.kaoyanDesktop;
      const desktopComplete = await desktop?.getSetupComplete?.();
      if (configured(models) && legacyComplete && !desktopComplete) await desktop?.setSetupComplete?.();
      setComplete(configured(models) && Boolean(desktopComplete || legacyComplete));
    } catch { setError('本地服务暂不可用。请重试，或检查桌面端的服务状态。'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const change = (value: ModelSettingsValue) => { setDraft(value); setSaved(false); setError(''); };
  const save = async () => {
    if (!draft || transitionLock.current) return;
    setBusy(true); setError('');
    try {
      const response = await post('/system/settings/model-profiles', { activate: true,
        profile: { ...draft, id: draft.editing_profile_id, name: draft.profile_name } }, 20000);
      if (!response.success) throw new Error('模型配置未保存');
      const persisted = await get('/system/settings', 20000);
      const value = persisted.data?.models as ModelSettingsValue;
      setDraft(value);
      if (!configured(value)) throw new Error('请填写回答模型和所需 API Key，再保存配置。');
      setSaved(true); navigate(2);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败，请重试'); }
    finally { setBusy(false); }
  };
  const test = async (role: ModelRoleId) => {
    try {
      const response = await post('/system/settings/models/test', { role, settings: draft }, 30000);
      return { success: Boolean(response.success), message: response.message || '连接检查完成' };
    } catch { return { success: false, message: '连接失败，请检查配置后重试' }; }
  };
  const nativeModel = draft?.models.find((model) => model.provider === draft.roles.vision.provider && model.id === draft.roles.vision.model);
  const finish = async () => {
    if (!saved || busy) return;
    setBusy(true); setError('');
    try {
      if (window.kaoyanDesktop?.setSetupComplete && !await window.kaoyanDesktop.setSetupComplete()) throw new Error('无法保存首次配置完成状态，请重试。');
      localStorage.setItem(KEY, '1'); setComplete(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败，请重试'); }
    finally { setBusy(false); }
  };
  const nativeProvider = draft?.providers.find((provider) => provider.id === draft.roles.vision.provider);
  const nativeUnsupported = draft?.multimodal_mode === 'native' && (!nativeProvider?.capabilities.includes('vision') || (nativeModel && !nativeModel.capabilities.includes('vision')));
  if (complete) return children;
  return <div className="welcome-screen">
    <header className="welcome-brand window-drag-region"><div className="welcome-brand-group"><img src="/brand/texa-mark.svg" alt="" /><span>Texa</span></div><span className="welcome-step" aria-label={`第 ${step + 1} 页，共 3 页`}>{step + 1} / 3</span></header>
    <main className="welcome-main" ref={mainRef}><div className={`welcome-content is-${phase} is-${direction}`} aria-busy={phase !== 'idle'}>
      {step === 0 && <><div className="welcome-leading"><p className="welcome-eyebrow">为学习而准备</p></div><h1 ref={headingRef} tabIndex={-1}>你好，欢迎来到 Texa。</h1><p className="welcome-lead">从一个问题开始，把难懂的知识慢慢讲清楚。围绕教材寻找依据、记录错因，在复习中连接知识，让每一次理解都成为积累。</p><div className="welcome-features"><span>有依据的解答</span><span>持续积累的错题</span><span>由你发起的学习目标</span></div><button className="app-primary-button welcome-primary" onClick={() => navigate(1)} disabled={loading || !draft || phase !== 'idle'}>开始设置 <ArrowRight size={16} /></button><p className="welcome-note">先连接回答模型；教材和复习记录可以之后慢慢加入。</p></>}
      {step === 1 && <><div className="welcome-leading"><p className="welcome-eyebrow">首次设置</p></div><h1 ref={headingRef} tabIndex={-1}>连接回答模型</h1><p className="welcome-lead">选择模型服务并填写所需凭证。凭证保存在本机。</p>{draft && <ModelSettingsManager guided value={draft} onChange={change} onTestConnection={test}
        onActivateProfile={async (id) => { try { const response = await post(`/system/settings/model-profiles/${encodeURIComponent(id)}/activate`, {}); if (!response.success) throw new Error(); await load(); } catch { setError('切换方案失败，请重试'); } }}
        onDeleteProfile={async (id) => { try { const response = await del(`/system/settings/model-profiles/${encodeURIComponent(id)}`); if (!response.success) throw new Error(); await load(); } catch { setError('删除方案失败，请重试'); } }} />}
        <div className="welcome-actions"><button className="app-primary-button welcome-primary" onClick={() => void save()} disabled={busy || loading || !draft || phase !== 'idle' || nativeUnsupported}>{busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}保存并继续</button><button className="app-ghost-button" onClick={() => navigate(0)} disabled={busy || phase !== 'idle'}><ArrowLeft size={16} />返回</button></div></>}
      {step === 2 && <><div className="welcome-leading"><span className="welcome-ready" role="img" aria-label="配置已保存"><Check size={15} /></span></div><h1 ref={headingRef} tabIndex={-1}>学习工作区已就绪</h1><p className="welcome-lead">从一个问题开始，教材和复习记录可以随时加入。</p><div className="welcome-final-actions"><button className="app-primary-button welcome-primary" disabled={!saved || busy || phase !== 'idle'} onClick={() => void finish()}>进入学习工作区 <ArrowRight size={16} /></button><button className="app-ghost-button" onClick={() => navigate(1)} disabled={busy || phase !== 'idle'}>返回模型配置</button></div></>}
      {loading && <p role="status" className="welcome-note">正在读取本地配置…</p>}{error && <div role="alert" className="welcome-error"><p>{error}</p><button className="app-secondary-button" onClick={() => void load()}>重新读取配置</button></div>}
    </div></main><footer className="welcome-footer">Texa · 为每一次理解，留下积累</footer>
  </div>;
}
