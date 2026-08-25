import { ChevronDown, KeyRound } from 'lucide-react';
import { useMemo, useState } from 'react';

export type ModelRoleId = 'reasoning' | 'vision';

export type ProviderCatalogItem = {
  id: string;
  label: string;
  capabilities: string[];
  default_endpoint: string;
  default_models: Partial<Record<ModelRoleId, string>>;
  requires_api_key: boolean;
};

export type ModelSettingsValue = {
  providers: ProviderCatalogItem[];
  models: Array<{ provider: string; id: string; label: string; capabilities: string[] }>;
  roles: Record<ModelRoleId, { provider: string; model: string; credential_id: string; endpoint_id: string }>;
  credentials: Record<ModelRoleId, { configured: boolean; required: boolean; api_key?: string; value?: string }>;
  endpoints: Record<ModelRoleId, { base_url: string; is_default: boolean }>;
  multimodal_mode: 'split' | 'native';
  profiles?: Array<{ id: string; name: string; roles: Record<ModelRoleId, { provider: string; model: string; credential_id: string; endpoint_id: string }>; endpoints: Record<ModelRoleId, { base_url: string; is_default: boolean }>; multimodal_mode: 'split' | 'native' }>;
  active_profile_id?: string;
  editing_profile_id?: string;
  profile_name?: string;
  credential_status?: Record<string, boolean>;
};

type Props = {
  value: ModelSettingsValue;
  onChange: (value: ModelSettingsValue) => void;
  compact?: boolean;
};

const roleMeta: Record<ModelRoleId, { title: string; description: string; capability: string }> = {
  reasoning: { title: '推理模型', description: '负责问答、讲解与文本推理', capability: 'text' },
  vision: { title: '识图模型', description: '负责题目图片、公式与图形关系识别', capability: 'vision' },
};

function fieldClass() {
  return 'w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none focus:border-accent focus:ring-2 focus:ring-[var(--accent-soft)]';
}

export default function ModelSettingsForm({ value, onChange, compact = false }: Props) {
  const [advanced, setAdvanced] = useState(false);
  const providersById = useMemo(() => Object.fromEntries(value.providers.map((item) => [item.id, item])), [value.providers]);

  const updateProvider = (role: ModelRoleId, providerId: string) => {
    const provider = providersById[providerId];
    if (!provider) return;
    onChange({
      ...value,
      roles: { ...value.roles, [role]: { ...value.roles[role], provider: providerId, model: provider.default_models[role] || '', credential_id: providerId } },
      credentials: { ...value.credentials, [role]: { configured: Boolean(value.credential_status?.[providerId]), required: provider.requires_api_key, api_key: '' } },
      endpoints: { ...value.endpoints, [role]: { base_url: provider.default_endpoint, is_default: true } },
    });
  };

  const updateRole = (role: ModelRoleId, model: string) => onChange({
    ...value,
    roles: { ...value.roles, [role]: { ...value.roles[role], model } },
  });

  const updateCredential = (role: ModelRoleId, apiKey: string) => onChange({
    ...value,
    credentials: { ...value.credentials, [role]: { ...value.credentials[role], api_key: apiKey } },
  });

  const updateEndpoint = (role: ModelRoleId, baseUrl: string) => onChange({
    ...value,
    endpoints: { ...value.endpoints, [role]: { base_url: baseUrl, is_default: baseUrl === providersById[value.roles[role].provider]?.default_endpoint } },
  });

  return (
    <div className={compact ? 'space-y-4' : 'space-y-5'}>
      <div className="divide-y divide-border rounded-xl border border-border bg-bg-card">
        {(['reasoning', 'vision'] as ModelRoleId[]).map((role) => {
          const meta = roleMeta[role];
          const roleValue = value.roles[role];
          const credential = value.credentials[role];
          const options = value.providers.filter((item) => item.capabilities.includes(meta.capability));
          const modelOptions = value.models.filter((item) => item.provider === roleValue.provider && item.capabilities.includes(meta.capability));
          const listId = `models-${role}`;
          return (
            <fieldset key={role} className="grid gap-4 p-4 sm:grid-cols-2">
              <legend className="sr-only">{meta.title}</legend>
              <div className="sm:col-span-2">
                <div className="text-sm font-semibold text-text-primary">{meta.title}</div>
                <div className="mt-0.5 text-xs text-text-secondary">{meta.description}</div>
              </div>
              <label className="grid gap-1.5 text-xs font-medium text-text-secondary">
                服务商
                <select value={roleValue.provider} onChange={(event) => updateProvider(role, event.target.value)} className={fieldClass()}>
                  {options.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
              {roleValue.provider === 'openai_compatible' && <label className="grid gap-1.5 text-xs font-medium text-text-secondary sm:col-span-2">服务地址<input value={value.endpoints[role].base_url} onChange={(event) => updateEndpoint(role, event.target.value)} placeholder="https://example.com/v1" className={fieldClass()} spellCheck={false} /></label>}
              <label className="grid gap-1.5 text-xs font-medium text-text-secondary">
                模型名
                <input list={listId} value={roleValue.model} onChange={(event) => updateRole(role, event.target.value)} className={fieldClass()} autoComplete="off" />
                <datalist id={listId}>{modelOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</datalist>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-text-secondary sm:col-span-2">
                <span className="flex items-center gap-1.5"><KeyRound className="h-3.5 w-3.5" />API Key（{credential.configured ? '已配置' : credential.required ? '未配置' : '无需配置'}）</span>
                <input type="password" autoComplete="new-password" value={credential.api_key || ''} disabled={!credential.required && roleValue.provider !== 'openai_compatible'} onChange={(event) => updateCredential(role, event.target.value)} placeholder={credential.required || roleValue.provider === 'openai_compatible' ? '留空则保留原值' : '当前连接不需要 API Key'} className={fieldClass()} />
              </label>
            </fieldset>
          );
        })}
      </div>

      <label className="grid gap-1.5 text-xs font-medium text-text-secondary">
        图片任务处理方式
        <select value={value.multimodal_mode} onChange={(event) => onChange({ ...value, multimodal_mode: event.target.value as 'split' | 'native' })} className={fieldClass()}>
          <option value="split">识图 / 推理分离</option>
          <option value="native">集成回复</option>
        </select>
      </label>

      <div>
        <button type="button" aria-expanded={advanced} onClick={() => setAdvanced((open) => !open)} className="app-secondary-button min-h-9 px-3 text-xs">
          <ChevronDown className={`h-4 w-4 transition-transform ${advanced ? 'rotate-180' : ''}`} />高级连接参数
        </button>
        {advanced && (
          <div className="mt-3 grid gap-4 rounded-xl border border-border bg-bg-secondary/50 p-4 sm:grid-cols-2">
            {(['reasoning', 'vision'] as ModelRoleId[]).filter((role) => value.roles[role].provider !== 'openai_compatible').map((role) => (
              <label key={role} className="grid gap-1.5 text-xs font-medium text-text-secondary">
                {value.multimodal_mode === 'native' ? (role === 'reasoning' ? '普通问答连接' : '图片任务连接') : roleMeta[role].title} Base URL
                <input value={value.endpoints[role].base_url} onChange={(event) => updateEndpoint(role, event.target.value)} placeholder="https://example.com/v1" className={fieldClass()} spellCheck={false} />
                <span className="font-normal leading-5">支持 OpenAI-compatible 服务与本地兼容接口。</span>
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
