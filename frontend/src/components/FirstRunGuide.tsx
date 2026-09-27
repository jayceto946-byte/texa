import { useEffect, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Check, Loader2 } from 'lucide-react';
import { get, post, del } from '../api/client';
import ModelSettingsManager from './settings/ModelSettingsManager';
import type { ModelRoleId, ModelSettingsValue } from './settings/ModelSettingsForm';
import './Welcome.css';

const KEY = 'texa:setup-complete:v3';
const configured = (value: ModelSettingsValue | null) => Boolean(value?.roles.reasoning.model &&
  (!value.credentials.reasoning.required || value.credentials.reasoning.configured));

export default function FirstRunGuide({ children }: { children: ReactNode }) {
  const [complete, setComplete] = useState(false);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<ModelSettingsValue | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = async () => {
    setLoading(true); setError('');
    try {
      const response = await get('/system/settings', 20000);
      if (!response.success || !response.data?.models) throw new Error('暂时无法读取模型配置');
      const models = response.data.models as ModelSettingsValue;
      setDraft(models); setSaved(configured(models));
      // Existing configured installations keep their workspace. New installations
      // finish setup explicitly; the flag never contains credentials.
      setComplete(configured(models) && (localStorage.getItem(KEY) === '1' || localStorage.getItem('kaoyan:onboarding-complete:v2') === '1'));
    } catch { setError('本地服务暂不可用。请重试，或检查桌面端的服务状态。'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const change = (value: ModelSettingsValue) => { setDraft(value); setSaved(false); setError(''); };
  const save = async () => {
    if (!draft) return;
    setBusy(true); setError('');
    try {
      const response = await post('/system/settings/model-profiles', { activate: true,
        profile: { ...draft, id: draft.editing_profile_id, name: draft.profile_name } }, 20000);
      if (!response.success) throw new Error('模型配置未保存');
      const persisted = await get('/system/settings', 20000);
      const value = persisted.data?.models as ModelSettingsValue;
      setDraft(value);
      if (!configured(value)) throw new Error('请填写回答模型和所需 API Key，再保存配置。');
      setSaved(true); setStep(2);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败，请重试'); }
    finally { setBusy(false); }
  };
  const test = async (role: ModelRoleId) => {
    try {
      const response = await post('/system/settings/models/test', { role, settings: draft }, 30000);
      return { success: Boolean(response.success), message: response.message || '连接检查完成' };
    } catch { return { success: false, message: '连接失败，请检查配置后重试' }; }
  };
  if (complete) return children;
  return <div className="welcome-screen">
    <header className="welcome-brand window-drag-region"><img src="/brand/texa-mark.svg" alt="" /><span>Texa</span><span className="welcome-step">{step + 1} / 3</span></header>
    <main className={`welcome-content ${step === 1 ? 'welcome-connect' : ''}`}>
      {step === 0 && <><p className="welcome-eyebrow">你的学习，从这里开始</p><h1>你好，欢迎来到 Texa。</h1><p className="welcome-lead">把问题讲清楚，把知识连起来。<br />为下一次进步，留下一份可以回看的学习记录。</p><div className="welcome-features"><span>有依据的解答</span><span>持续积累的错题</span><span>由你发起的学习目标</span></div><button className="app-primary-button" onClick={() => setStep(1)} disabled={loading || !draft}>开始设置 <ArrowRight size={16} /></button><p className="welcome-note">先连接回答模型。教材可以在进入工作区后添加。</p></>}
      {step === 1 && <><p className="welcome-eyebrow">连接你的回答模型</p><h1>选择一个学习伙伴。</h1><p className="welcome-lead">使用自己的模型服务。凭证保存在本机，问题与必要上下文会发送给你选择的服务。</p>{draft && <ModelSettingsManager guided value={draft} onChange={change} onTestConnection={test}
        onActivateProfile={async (id) => { try { const response = await post(`/system/settings/model-profiles/${encodeURIComponent(id)}/activate`, {}); if (!response.success) throw new Error(); await load(); } catch { setError('切换方案失败，请重试'); } }}
        onDeleteProfile={async (id) => { try { const response = await del(`/system/settings/model-profiles/${encodeURIComponent(id)}`); if (!response.success) throw new Error(); await load(); } catch { setError('删除方案失败，请重试'); } }} />}
        <div className="welcome-actions"><button className="app-ghost-button" onClick={() => setStep(0)} disabled={busy}><ArrowLeft size={16} />返回</button><button className="app-primary-button" onClick={() => void save()} disabled={busy || loading || !draft}>{busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}保存并继续</button></div></>}
      {step === 2 && <><div className="welcome-ready"><Check size={30} /></div><p className="welcome-eyebrow">准备好了</p><h1>很高兴与你一起学习。</h1><p className="welcome-lead">从一个问题开始，或为自己设定一个目标。<br />教材、图片题和复习记录，随时都可以加入。</p><button className="app-primary-button" disabled={!saved} onClick={() => { localStorage.setItem(KEY, '1'); setComplete(true); }}>进入学习工作区 <ArrowRight size={16} /></button><button className="app-ghost-button" onClick={() => setStep(1)}>返回模型配置</button></>}
      {loading && <p role="status" className="welcome-note">正在读取本地配置…</p>}{error && <div role="alert" className="welcome-error"><p>{error}</p><button className="app-secondary-button" onClick={() => void load()}>重新读取配置</button></div>}
    </main><footer className="welcome-footer">Texa · 为每一次理解，留下积累</footer>
  </div>;
}
