import { ChevronDown, Link2, LoaderCircle, Plus, Trash2 } from 'lucide-react';
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
  vision: { title: '独立视觉模型', capability: 'vision' },
};

const controlClass = 'settings-form-control';
const fieldRowClass = 'settings-form-row';

export default function ModelSettingsManager({ value, onChange, onActivateProfile, onDeleteProfile, onTestConnection }: Props) {
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [testingRole, setTestingRole] = useState<ModelRoleId | null>(null);
  const [testResults, setTestResults] = useState<Partial<Record<ModelRoleId, { success: boolean; message: string }>>>({});
  const remembered = useRef<Record<string, { model: string; displayName?: string; endpoint: string; credentialId: string; configured: boolean; apiKey: string }>>({});
  const providersById = useMemo(() => Object.fromEntries(value.providers.map((item) => [item.id, item])), [value.providers]);
  const profiles = value.profiles || [];
  const editingSavedProfile = profiles.some((profile) => profile.id === value.editing_profile_id);
  const profileSelectValue = editingSavedProfile ? value.editing_profile_id! : '__draft__';
  const reasoningRole: ModelRoleId = value.multimodal_mode === 'native' ? 'vision' : 'reasoning';
  const connectedRoles: ModelRoleId[] = value.multimodal_mode === 'native' ? ['vision'] : ['reasoning', 'vision'];
  const connectionExpanded = connectionsOpen;

  const changeMode = (mode: 'split' | 'native') => {
    if (mode === 'split') {
      onChange({ ...value, multimodal_mode: mode });
      return;
    }
    onChange({
      ...value,
      multimodal_mode: mode,
      roles: { ...value.roles, reasoning: { ...value.roles.vision, endpoint_id: 'reasoning' } },
      credentials: { ...value.credentials, reasoning: { ...value.credentials.vision } },
      endpoints: { ...value.endpoints, reasoning: { ...value.endpoints.vision } },
    });
  };

  const selectProvider = (role: ModelRoleId, providerId: string) => {
    const current = value.roles[role];
    remembered.current[`${role}:${current.provider}`] = {
      model: current.model,
      displayName: current.display_name,
      endpoint: value.endpoints[role].base_url,
      credentialId: current.credential_id,
      configured: value.credentials[role].configured,
      apiKey: value.credentials[role].api_key || '',
    };
    const provider = providersById[providerId];
    const previous = remembered.current[`${role}:${providerId}`];
    if (!provider) return;
    const credentialId = previous?.credentialId || (providerId === 'openai_compatible' ? `${value.editing_profile_id || 'draft'}-${role}-custom` : providerId);
    const nextRole = {
      ...current,
      provider: providerId,
      model: previous?.model || provider.default_models[role] || '',
      display_name: previous?.displayName,
      credential_id: credentialId,
    };
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

  const updateModel = (role: ModelRoleId, model: string, displayName?: string) => {
    const roleValue = value.roles[role];
    const syncIntegrated = value.multimodal_mode === 'native' && role === 'vision';
    onChange({
      ...value,
      roles: {
        ...value.roles,
        [role]: { ...roleValue, model, display_name: displayName },
        ...(syncIntegrated ? { reasoning: { ...value.roles.reasoning, provider: roleValue.provider, model, display_name: displayName, credential_id: roleValue.credential_id } } : {}),
      },
    });
  };

  const updateCredential = (role: ModelRoleId, apiKey: string) => {
    const nextCredential = { ...value.credentials[role], api_key: apiKey };
    const syncIntegrated = value.multimodal_mode === 'native' && role === 'vision';
    onChange({ ...value, credentials: { ...value.credentials, [role]: nextCredential, ...(syncIntegrated ? { reasoning: { ...nextCredential } } : {}) } });
  };

  const updateEndpoint = (role: ModelRoleId, baseUrl: string) => {
    const endpoint = { base_url: baseUrl, is_default: false };
    const syncIntegrated = value.multimodal_mode === 'native' && role === 'vision';
    onChange({ ...value, endpoints: { ...value.endpoints, [role]: endpoint, ...(syncIntegrated ? { reasoning: { ...endpoint } } : {}) } });
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

  const renderRoleFields = (role: ModelRoleId, title: string) => {
    const meta = roleMeta[role];
    const roleValue = value.roles[role];
    const credential = value.credentials[role];
    const requiredCapabilities = value.multimodal_mode === 'native' && role === 'vision' ? ['text', 'vision'] : [meta.capability];
    const providers = value.providers.filter((item) => requiredCapabilities.every((capability) => item.capabilities.includes(capability)));
    const models = value.models.filter((item) => item.provider === roleValue.provider && requiredCapabilities.every((capability) => item.capabilities.includes(capability)));
    const isCustom = roleValue.provider === 'openai_compatible';
    const acceptsCredential = credential.required || isCustom;
    const credentialLabel = credential.configured ? '已配置' : isCustom ? '可选' : credential.required ? '未配置' : '无需配置';

    return (
      <div className="settings-subsection">
        <h4 className="settings-section-title">{title}</h4>
        <div className={fieldRowClass}>
          <span className="settings-label">Provider</span>
          <ScrollableSelect
            compact
            ariaLabel={`${title} Provider`}
            value={roleValue.provider}
            options={providers.map((provider) => ({ value: provider.id, label: provider.label }))}
            onChange={(providerId) => selectProvider(role, providerId)}
          />
        </div>
        <ModelPicker
          role={role}
          title={title}
          model={roleValue.model}
          displayName={roleValue.display_name || ''}
          models={models}
          onChange={(model, displayName) => updateModel(role, model, displayName)}
        />
        {isCustom && (
          <div className={fieldRowClass}>
            <label htmlFor={`${role}-custom-base-url`} className="settings-label">Base URL</label>
            <div className="min-w-0">
              <input id={`${role}-custom-base-url`} value={value.endpoints[role].base_url} onChange={(event) => updateEndpoint(role, event.target.value)} placeholder="https://example.com/v1" className={controlClass} autoComplete="url" spellCheck={false} />
              <p className="mt-1 settings-secondary">填写 OpenAI-compatible API 地址。</p>
            </div>
          </div>
        )}
        <div className={fieldRowClass}>
          <label htmlFor={`${role}-api-key`} className="settings-label">API Key</label>
          <div className="min-w-0">
            <input id={`${role}-api-key`} type="password" autoComplete="new-password" value={credential.api_key || ''} disabled={!acceptsCredential} onChange={(event) => updateCredential(role, event.target.value)} placeholder={acceptsCredential ? '留空保留现有密钥' : '无需填写'} className={controlClass} />
            <p className={`mt-1 settings-secondary ${credential.configured ? 'text-[var(--success)]' : ''}`}>{credentialLabel}</p>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="settings-model-manager">
      <header className="settings-page-header">
        <h3>模型配置</h3>
        <p>管理 Texa 使用的模型、凭据与连接信息。</p>
      </header>

      <section aria-labelledby="profile-heading" className="settings-section">
        <h4 id="profile-heading" className="settings-section-title">模型方案</h4>
        <div className={fieldRowClass}>
          <span className="settings-label">方案</span>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
            <ScrollableSelect
              compact
              ariaLabel="模型方案"
              className="min-w-0 flex-1"
              value={profileSelectValue}
              options={[
                ...(!editingSavedProfile ? [{ value: '__draft__', label: '新方案', description: '未保存' }] : []),
                ...profiles.map((profile) => ({ value: profile.id, label: profile.name, description: profile.id === value.active_profile_id ? '当前方案' : undefined })),
              ]}
              onChange={(profileId) => { if (profileId !== '__draft__') onActivateProfile(profileId); }}
            />
            <button type="button" onClick={newProfile} className="app-secondary-button flex-none px-3"><Plus className="h-4 w-4" />新建方案</button>
          </div>
        </div>
        <div className={fieldRowClass}>
          <label htmlFor="profile-name" className="settings-label">方案名称</label>
          <div className="flex min-w-0 gap-2">
            <input id="profile-name" value={value.profile_name || ''} onChange={(event) => onChange({ ...value, profile_name: event.target.value })} className={`${controlClass} min-w-0 flex-1`} />
            {value.editing_profile_id && value.editing_profile_id !== value.active_profile_id && editingSavedProfile && (
              <button type="button" onClick={() => onDeleteProfile(value.editing_profile_id!)} className="settings-danger-action"><Trash2 className="h-4 w-4" />删除</button>
            )}
          </div>
        </div>
      </section>

      <section aria-labelledby="models-heading" className="settings-section">
        <h4 id="models-heading" className="settings-section-title">模型</h4>
        {renderRoleFields(reasoningRole, '推理模型')}

        <div className="settings-subsection">
          <h4 className="settings-section-title">视觉模型</h4>
          <div className={fieldRowClass}>
            <span className="settings-label">处理方式</span>
            <div className="min-w-0">
              <ScrollableSelect
                compact
                ariaLabel="视觉模型处理方式"
                value={value.multimodal_mode}
                options={[
                  { value: 'native', label: '使用推理模型' },
                  { value: 'split', label: '使用独立视觉模型' },
                ]}
                onChange={(mode) => changeMode(mode as 'split' | 'native')}
              />
              <p className="mt-1 settings-secondary">
                {value.multimodal_mode === 'native' ? '当前模型支持视觉输入时，直接处理图片并生成回复。' : '先由独立视觉模型理解图片，再交给推理模型生成回复。'}
              </p>
            </div>
          </div>
          {value.multimodal_mode === 'split' && renderRoleFields('vision', '独立视觉模型')}
        </div>
      </section>

      <section aria-labelledby="connection-heading" className="settings-section">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 id="connection-heading" className="settings-section-title">连接</h4>
            <p className="mt-1 settings-secondary">默认 Base URL 通常无需修改。</p>
          </div>
          <button type="button" aria-expanded={connectionExpanded} onClick={() => setConnectionsOpen((open) => !open)} className="app-ghost-button">
            <ChevronDown className={`h-4 w-4 transition-transform ${connectionExpanded ? 'rotate-180' : ''}`} />
            {connectionExpanded ? '收起连接设置' : '展开连接设置'}
          </button>
        </div>
        {connectionExpanded && (
          <div className="mt-4 space-y-4">
            {connectedRoles.map((role) => {
              const label = value.multimodal_mode === 'native' ? '推理模型' : roleMeta[role].title;
              const result = testResults[role];
              return (
                <div key={role} className="space-y-3">
                  {value.roles[role].provider !== 'openai_compatible' && (
                    <div className={fieldRowClass}>
                      <label htmlFor={`${role}-base-url`} className="settings-label">{label} Base URL</label>
                      <input id={`${role}-base-url`} value={value.endpoints[role].base_url} onChange={(event) => updateEndpoint(role, event.target.value)} placeholder="https://example.com/v1" className={controlClass} spellCheck={false} />
                    </div>
                  )}
                  <div className={fieldRowClass}>
                    <span aria-hidden="true" />
                    <div className="flex min-w-0 flex-wrap items-center gap-3">
                      <button type="button" onClick={() => void testConnection(role)} disabled={testingRole !== null || !value.roles[role].model.trim()} className="app-secondary-button">
                        {testingRole === role ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                        {testingRole === role ? '测试中' : `测试${label}连接`}
                      </button>
                      {result && <span role="status" className={`min-w-0 settings-secondary ${result.success ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}>{result.message}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function ModelPicker({ role, title, model, displayName, models, onChange }: { role: ModelRoleId; title: string; model: string; displayName: string; models: ModelSettingsValue['models']; onChange: (model: string, displayName?: string) => void }) {
  const isSuggested = models.some((item) => item.id === model);
  const options = [
    ...models.map((item) => ({ value: item.id, label: item.label, description: item.label === item.id ? undefined : item.id })),
    ...(!isSuggested ? [{ value: '__current_custom__', label: displayName || model || '未命名自定义模型', description: model || '等待填写 Model ID' }] : []),
    { value: '__new_custom__', label: '添加自定义模型…' },
  ];
  return (
    <>
      <div className={fieldRowClass}>
        <span className="settings-label">Model</span>
        <ScrollableSelect
          compact
          ariaLabel={`${title} Model`}
          value={isSuggested ? model : '__current_custom__'}
          options={options}
          showSelectedDescription={false}
          onChange={(nextValue) => {
            if (nextValue === '__new_custom__') onChange('', '');
            else if (nextValue !== '__current_custom__') onChange(nextValue, undefined);
          }}
        />
      </div>
      {!isSuggested && (
        <>
          <div className={fieldRowClass}>
            <label htmlFor={`${role}-custom-model-name`} className="settings-label">显示名称</label>
            <input id={`${role}-custom-model-name`} value={displayName} onChange={(event) => onChange(model, event.target.value)} placeholder="例如：课程专用 Qwen" className={controlClass} autoComplete="off" />
          </div>
          <div className={fieldRowClass}>
            <label htmlFor={`${role}-custom-model-id`} className="settings-label">Model ID</label>
            <input id={`${role}-custom-model-id`} value={model} onChange={(event) => onChange(event.target.value, displayName)} placeholder="例如：qwen3.7-plus" className={controlClass} autoComplete="off" spellCheck={false} />
          </div>
        </>
      )}
    </>
  );
}
