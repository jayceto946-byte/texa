import { Check, ChevronDown, ChevronLeft, ChevronRight, KeyRound, Link2, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import ScrollableSelect from '../ui/ScrollableSelect';
import type { ModelRoleId, ModelSettingsValue } from './ModelSettingsForm';

type Props = {
  value: ModelSettingsValue & {
    profiles?: Array<{ id: string; name: string }>;
    active_profile_id?: string;
    editing_profile_id?: string;
    profile_name?: string;
    credential_status?: Record<string, boolean>;
  };
  onChange: (value: Props['value']) => void;
  onActivateProfile: (profileId: string) => void;
  onDeleteProfile: (profileId: string) => void;
  onTestConnection: (role: ModelRoleId) => Promise<{ success: boolean; message: string }>;
};

const roleMeta: Record<ModelRoleId, { title: string; capability: string }> = {
  reasoning: { title: '推理模型', capability: 'text' },
  vision: { title: '识图模型', capability: 'vision' },
};
const controlClass = 'w-full rounded-md border border-border bg-bg-primary px-3 py-2.5 text-sm text-text-primary outline-none focus:border-accent focus:ring-2 focus:ring-[var(--accent-soft)]';

export default function ModelSettingsManager({ value, onChange, onActivateProfile, onDeleteProfile, onTestConnection }: Props) {
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [testingRole, setTestingRole] = useState<ModelRoleId | null>(null);
  const [testResults, setTestResults] = useState<Partial<Record<ModelRoleId, { success: boolean; message: string }>>>({});
  const remembered = useRef<Record<string, { model: string; endpoint: string; credentialId: string; configured: boolean; apiKey: string }>>({});
  const profileRail = useRef<HTMLDivElement>(null);
  const providersById = useMemo(() => Object.fromEntries(value.providers.map((item) => [item.id, item])), [value.providers]);
  const configuredRoles: ModelRoleId[] = value.multimodal_mode === 'native' ? ['vision'] : ['reasoning', 'vision'];

  const changeMode = (mode: 'split' | 'native') => {
    if (mode === 'split') {
      onChange({ ...value, multimodal_mode: mode });
      return;
    }
    onChange({
      ...value,
      multimodal_mode: mode,
      roles: {
        ...value.roles,
        reasoning: { ...value.roles.vision, endpoint_id: 'reasoning' },
      },
      credentials: { ...value.credentials, reasoning: { ...value.credentials.vision } },
      endpoints: { ...value.endpoints, reasoning: { ...value.endpoints.vision } },
    });
  };

  const selectProvider = (role: ModelRoleId, providerId: string) => {
    const current = value.roles[role];
    remembered.current[`${role}:${current.provider}`] = {
      model: current.model,
      endpoint: value.endpoints[role].base_url,
      credentialId: current.credential_id,
      configured: value.credentials[role].configured,
      apiKey: value.credentials[role].api_key || '',
    };
    const provider = providersById[providerId];
    const previous = remembered.current[`${role}:${providerId}`];
    if (!provider) return;
    const credentialId = previous?.credentialId || (providerId === 'openai_compatible'
      ? `${value.editing_profile_id || 'draft'}-${role}-custom`
      : providerId);
    const nextRole = { ...current, provider: providerId, model: previous?.model || provider.default_models[role] || '', credential_id: credentialId };
    const nextCredential = { configured: previous?.configured ?? Boolean(value.credential_status?.[credentialId]), required: provider.requires_api_key, api_key: previous?.apiKey || '' };
    const nextEndpoint = { base_url: previous?.endpoint ?? provider.default_endpoint, is_default: !previous };
    const syncIntegrated = value.multimodal_mode === 'native' && role === 'vision';
    onChange({
      ...value,
      roles: { ...value.roles, [role]: nextRole, ...(syncIntegrated ? { reasoning: { ...nextRole, endpoint_id: 'reasoning' } } : {}) },
      credentials: { ...value.credentials, [role]: nextCredential, ...(syncIntegrated ? { reasoning: { ...nextCredential } } : {}) },
      endpoints: { ...value.endpoints, [role]: nextEndpoint, ...(syncIntegrated ? { reasoning: { ...nextEndpoint } } : {}) },
    });
  };

  const newProfile = () => {
    const id = `profile-${Date.now().toString(36)}`;
    const roles = { ...value.roles };
    const credentials = { ...value.credentials };
    (['reasoning', 'vision'] as ModelRoleId[]).forEach((role) => {
      if (roles[role].provider !== 'openai_compatible') return;
      roles[role] = { ...roles[role], credential_id: `${id}-${role}-custom` };
      credentials[role] = { ...credentials[role], configured: false, api_key: '' };
    });
    onChange({ ...value, roles, credentials, editing_profile_id: id, profile_name: '新方案' });
  };
  const scrollProfiles = (direction: number) => profileRail.current?.scrollBy({ left: direction * 280, behavior: 'smooth' });
  const testConnection = async (role: ModelRoleId) => {
    setTestingRole(role);
    setTestResults((current) => ({ ...current, [role]: undefined }));
    try {
      const result = await onTestConnection(role);
      setTestResults((current) => ({ ...current, [role]: result }));
    } finally {
      setTestingRole(null);
    }
  };

  return (
    <div className="space-y-6">
      <section aria-labelledby="profile-heading" className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 id="profile-heading" className="text-base font-semibold text-text-primary">模型方案</h3>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => scrollProfiles(-1)} className="app-ghost-button h-9 w-9 p-0" aria-label="向前浏览方案"><ChevronLeft className="h-4 w-4" /></button>
            <button type="button" onClick={() => scrollProfiles(1)} className="app-ghost-button h-9 w-9 p-0" aria-label="向后浏览方案"><ChevronRight className="h-4 w-4" /></button>
            <button type="button" onClick={newProfile} className="app-secondary-button min-h-9 px-3 text-sm"><Plus className="h-4 w-4" />新建</button>
          </div>
        </div>
        <div ref={profileRail} className="flex snap-x snap-mandatory gap-2 overflow-x-auto border-y border-border py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {(value.profiles || []).map((profile) => {
            const active = profile.id === value.active_profile_id;
            return (
              <button key={profile.id} type="button" onClick={() => { if (!active) onActivateProfile(profile.id); }} className={`flex min-w-52 snap-start items-center justify-between rounded-md border px-3 py-2.5 text-left text-sm transition-colors ${active ? 'border-accent bg-[var(--accent-soft)] text-text-primary' : 'border-border bg-bg-primary text-text-secondary hover:border-accent hover:text-text-primary'}`}>
                <span className="truncate font-medium">{profile.name}</span>
                {active && <Check className="h-4 w-4 flex-none text-accent" aria-label="当前方案" />}
              </button>
            );
          })}
          {!(value.profiles || []).length && <div className="px-1 py-2 text-sm text-text-secondary">尚未保存方案</div>}
        </div>
        <div className="flex items-end gap-2">
          <label className="min-w-0 flex-1 text-sm font-medium text-text-primary">方案名称<input value={value.profile_name || ''} onChange={(event) => onChange({ ...value, profile_name: event.target.value })} className={`${controlClass} mt-1.5`} /></label>
          {value.editing_profile_id && value.editing_profile_id !== value.active_profile_id && (value.profiles || []).some((item) => item.id === value.editing_profile_id) && (
            <button type="button" onClick={() => onDeleteProfile(value.editing_profile_id!)} className="app-ghost-button min-h-10 px-3 text-[var(--danger)]"><Trash2 className="h-4 w-4" />删除</button>
          )}
        </div>
      </section>

      <label className="block text-sm font-medium text-text-primary">图片任务处理方式<select value={value.multimodal_mode} onChange={(event) => changeMode(event.target.value as 'split' | 'native')} className={`${controlClass} mt-1.5`}><option value="split">识图 / 推理分离</option><option value="native">集成回复</option></select><span className="mt-1.5 block text-xs font-normal leading-5 text-text-secondary">{value.multimodal_mode === 'split' ? '识图模型提取题目与图形关系，再由推理模型生成回复。' : '一个多模态模型完成图片理解、推理与回复。'}</span></label>

      <div className="divide-y divide-border border-y border-border">
        {configuredRoles.map((role) => {
          const meta = roleMeta[role];
          const displayTitle = value.multimodal_mode === 'native' ? '集成模型' : meta.title;
          const roleValue = value.roles[role];
          const credential = value.credentials[role];
          const requiredCapabilities = value.multimodal_mode === 'native' ? ['text', 'vision'] : [meta.capability];
          const providers = value.providers.filter((item) => requiredCapabilities.every((capability) => item.capabilities.includes(capability)));
          const models = value.models.filter((item) => item.provider === roleValue.provider && requiredCapabilities.every((capability) => item.capabilities.includes(capability)));
          const isCustom = roleValue.provider === 'openai_compatible';
          const acceptsCredential = credential.required || isCustom;
          return (
            <fieldset key={role} className="space-y-4 py-5">
              <legend className="text-base font-semibold text-text-primary">{displayTitle}</legend>
              <ProviderRail label={`${displayTitle}服务商`} providers={providers} selected={roleValue.provider} onSelect={(providerId) => selectProvider(role, providerId)} />
              <div className="grid gap-4 sm:grid-cols-2">
                <ModelPicker role={role} title={displayTitle} model={roleValue.model} models={models} onChange={(model) => onChange({ ...value, roles: { ...value.roles, [role]: { ...roleValue, model }, ...(value.multimodal_mode === 'native' ? { reasoning: { ...value.roles.reasoning, provider: roleValue.provider, model, credential_id: roleValue.credential_id } } : {}) } })} />
                {isCustom && <label className="text-sm font-medium text-text-primary">服务地址<input value={value.endpoints[role].base_url} onChange={(event) => { const endpoint = { base_url: event.target.value, is_default: false }; onChange({ ...value, endpoints: { ...value.endpoints, [role]: endpoint, ...(value.multimodal_mode === 'native' ? { reasoning: { ...endpoint } } : {}) } }); }} placeholder="https://example.com/v1" className={`${controlClass} mt-1.5`} spellCheck={false} /></label>}
                <label className={`text-sm font-medium text-text-primary ${isCustom ? 'sm:col-span-2' : ''}`}><span className="flex items-center gap-2"><KeyRound className="h-4 w-4" />API Key <span className={credential.configured ? 'text-[var(--success)]' : 'text-text-secondary'}>{credential.configured ? '已配置' : isCustom ? '可选' : credential.required ? '未配置' : '无需配置'}</span></span><input type="password" autoComplete="new-password" value={credential.api_key || ''} disabled={!acceptsCredential} onChange={(event) => { const nextCredential = { ...credential, api_key: event.target.value }; onChange({ ...value, credentials: { ...value.credentials, [role]: nextCredential, ...(value.multimodal_mode === 'native' ? { reasoning: { ...nextCredential } } : {}) } }); }} placeholder={acceptsCredential ? '留空保留现有密钥' : '无需填写'} className={`${controlClass} mt-1.5`} /></label>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button type="button" onClick={() => void testConnection(role)} disabled={testingRole !== null || !roleValue.model.trim()} className="app-secondary-button min-h-9 px-3 text-sm">
                  {testingRole === role ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                  {testingRole === role ? '测试中' : '测试连接'}
                </button>
                {testResults[role] && <span role="status" className={`text-sm ${testResults[role]?.success ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}>{testResults[role]?.message}</span>}
              </div>
            </fieldset>
          );
        })}
      </div>

      <div>
        <button type="button" aria-expanded={connectionsOpen} onClick={() => setConnectionsOpen((open) => !open)} className="app-secondary-button min-h-9 px-3 text-sm"><ChevronDown className={`h-4 w-4 transition-transform ${connectionsOpen ? 'rotate-180' : ''}`} />连接设置</button>
        {connectionsOpen && <div className="mt-3 grid gap-4 border-t border-border pt-4 sm:grid-cols-2">
          {configuredRoles.filter((role) => value.roles[role].provider !== 'openai_compatible').map((role) => {
            const label = value.multimodal_mode === 'native' ? '集成模型' : roleMeta[role].title;
            return <label key={role} className="text-sm font-medium text-text-primary">{label}<input value={value.endpoints[role].base_url} onChange={(event) => onChange({ ...value, endpoints: { ...value.endpoints, [role]: { base_url: event.target.value, is_default: false } } })} placeholder="https://example.com/v1" className={`${controlClass} mt-1.5`} spellCheck={false} /></label>;
          })}
        </div>}
      </div>
    </div>
  );
}

function ModelPicker({ role, title, model, models, onChange }: { role: ModelRoleId; title: string; model: string; models: ModelSettingsValue['models']; onChange: (model: string) => void }) {
  const isSuggested = models.some((item) => item.id === model);
  const options = [
    ...models.map((item) => ({ value: item.id, label: item.label, description: item.label === item.id ? undefined : item.id })),
    { value: '__custom__', label: '自定义 model id…' },
  ];
  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-text-primary">常用型号</label>
      <ScrollableSelect ariaLabel={`${title}常用型号`} value={isSuggested ? model : '__custom__'} options={options} onChange={(nextValue) => onChange(nextValue === '__custom__' ? '' : nextValue)} />
      {!isSuggested && <label className="block text-sm font-medium text-text-primary">自定义模型名
        <input value={model} onChange={(event) => onChange(event.target.value)} placeholder={role === 'reasoning' ? '例如部署名或新模型 ID' : '例如视觉模型或本地部署名'} className={`${controlClass} mt-1.5`} autoComplete="off" spellCheck={false} />
      </label>}
    </div>
  );
}

function ProviderRail({ label, providers, selected, onSelect }: { label: string; providers: ModelSettingsValue['providers']; selected: string; onSelect: (providerId: string) => void }) {
  const rail = useRef<HTMLDivElement>(null);
  const scroll = (direction: number) => rail.current?.scrollBy({ left: direction * 260, behavior: 'smooth' });
  return (
    <div className="grid grid-cols-[36px_minmax(0,1fr)_36px] items-center gap-1">
      <button type="button" onClick={() => scroll(-1)} className="app-ghost-button h-9 w-9 p-0" aria-label={`${label}向前`}><ChevronLeft className="h-4 w-4" /></button>
      <div ref={rail} className="flex snap-x snap-mandatory gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label={label}>
        {providers.map((provider) => <button key={provider.id} type="button" onClick={() => onSelect(provider.id)} className={`min-w-max snap-start rounded-md border px-3 py-2 text-sm font-medium transition-colors ${selected === provider.id ? 'border-accent bg-[var(--accent-soft)] text-text-primary' : 'border-border bg-bg-primary text-text-secondary hover:border-accent hover:text-text-primary'}`}>{provider.label}</button>)}
      </div>
      <button type="button" onClick={() => scroll(1)} className="app-ghost-button h-9 w-9 p-0" aria-label={`${label}向后`}><ChevronRight className="h-4 w-4" /></button>
    </div>
  );
}
