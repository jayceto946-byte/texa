import { ChevronDown, Link2, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
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
  guided?: boolean;
};

const roleMeta: Record<ModelRoleId, { title: string; capability: string }> = {
  reasoning: { title: '推理模型', capability: 'text' },
  vision: { title: '独立视觉模型', capability: 'vision' },
};

const controlClass = 'app-field w-full';
const fieldRowClass = 'settings-form-row';
const guidedProviderLabels: Record<string, string> = {
  deepseek: 'DeepSeek', moonshot: 'Kimi', qwen: 'Qwen', gemini: 'Gemini',
  openai: 'OpenAI', ollama: 'Ollama（本地）', openai_compatible: '自定义服务',
};

export default function ModelSettingsManager({ value, onChange, onActivateProfile, onDeleteProfile, onTestConnection, guided = false }: Props) {
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [testingRole, setTestingRole] = useState<ModelRoleId | null>(null);
  const [testingFingerprint, setTestingFingerprint] = useState('');
  const [testResults, setTestResults] = useState<Partial<Record<ModelRoleId, { success: boolean; message: string; fingerprint: string }>>>({});
  const testSequence = useRef(0);
  const remembered = useRef<Record<string, { model: string; displayName?: string; endpoint: string; credentialId: string; configured: boolean; apiKey: string }>>({});
  const splitVision = useRef<{
    role: Props['value']['roles']['vision'];
    credential: Props['value']['credentials']['vision'];
    endpoint: Props['value']['endpoints']['vision'];
  } | null>(null);
  const providersById = useMemo(() => Object.fromEntries(value.providers.map((item) => [item.id, item])), [value.providers]);
  const profiles = value.profiles || [];
  const editingSavedProfile = profiles.some((profile) => profile.id === value.editing_profile_id);
  const profileSelectValue = editingSavedProfile ? value.editing_profile_id! : '__draft__';
  const reasoningRole: ModelRoleId = value.multimodal_mode === 'native' ? 'vision' : 'reasoning';
  const connectedRoles: ModelRoleId[] = value.multimodal_mode === 'native' ? ['vision'] : ['reasoning', 'vision'];
  const connectionExpanded = connectionsOpen;
  const fingerprint = (settings: Props['value'], role: ModelRoleId) => JSON.stringify([
    settings.multimodal_mode, settings.roles[role].provider, settings.roles[role].model,
    settings.roles[role].credential_id, settings.credentials[role].api_key,
    settings.credentials[role].configured, settings.endpoints[role].base_url,
  ]);
  const currentFingerprints = useRef<Record<ModelRoleId, string>>({ reasoning: '', vision: '' });
  useEffect(() => {
    currentFingerprints.current = { reasoning: fingerprint(value, 'reasoning'), vision: fingerprint(value, 'vision') };
  }, [value]);
  const invalidateTests = () => {
    ++testSequence.current;
    setTestingRole(null);
    setTestResults({});
  };

  const changeGuidedMode = (mode: 'split' | 'native') => {
    if (mode === value.multimodal_mode) return;
    invalidateTests();
    if (mode === 'native') {
      splitVision.current = { role: value.roles.vision, credential: value.credentials.vision, endpoint: value.endpoints.vision };
      onChange({ ...value, multimodal_mode: 'native',
        roles: { ...value.roles, vision: { ...value.roles.reasoning, endpoint_id: 'vision' } },
        credentials: { ...value.credentials, vision: { ...value.credentials.reasoning } },
        endpoints: { ...value.endpoints, vision: { ...value.endpoints.reasoning } },
      });
      return;
    }
    const previous = splitVision.current;
    onChange({ ...value, multimodal_mode: 'split',
      roles: { ...value.roles, ...(previous ? { vision: previous.role } : {}) },
      credentials: { ...value.credentials, ...(previous ? { vision: previous.credential } : {}) },
      endpoints: { ...value.endpoints, ...(previous ? { vision: previous.endpoint } : {}) },
    });
  };

  const selectProvider = (role: ModelRoleId, providerId: string) => {
    invalidateTests();
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
    invalidateTests();
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
    invalidateTests();
    const nextCredential = { ...value.credentials[role], api_key: apiKey };
    const syncIntegrated = value.multimodal_mode === 'native' && role === 'vision';
    onChange({ ...value, credentials: { ...value.credentials, [role]: nextCredential, ...(syncIntegrated ? { reasoning: { ...nextCredential } } : {}) } });
  };

  const updateEndpoint = (role: ModelRoleId, baseUrl: string) => {
    invalidateTests();
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
    const sequence = ++testSequence.current;
    const testedFingerprint = currentFingerprints.current[role];
    setTestingRole(role);
    setTestingFingerprint(testedFingerprint);
    setTestResults((current) => ({ ...current, [role]: undefined }));
    try {
      const result = await onTestConnection(role);
      if (sequence === testSequence.current && testedFingerprint === currentFingerprints.current[role]) {
        setTestResults((current) => ({ ...current, [role]: { ...result, fingerprint: testedFingerprint } }));
      }
    } finally {
      if (sequence === testSequence.current) setTestingRole(null);
    }
  };

  const renderGuidedRole = (role: ModelRoleId, title: string) => {
    const selected = value.roles[role];
    const credential = value.credentials[role];
    const capabilities = value.multimodal_mode === 'native' && role === 'vision' ? ['text', 'vision'] : [roleMeta[role].capability];
    const providers = value.providers.filter((item) => capabilities.every((capability) => item.capabilities.includes(capability)));
    const models = value.models.filter((item) => item.provider === selected.provider && capabilities.every((capability) => item.capabilities.includes(capability)));
    const knownModel = models.find((item) => item.id === selected.model);
    const cannotSeeImages = role === 'vision' && (knownModel ? !knownModel.capabilities.includes('vision') : !providersById[selected.provider]?.capabilities.includes('vision'));
    const unknownVision = role === 'vision' && !knownModel && !cannotSeeImages;
    const isCustom = selected.provider === 'openai_compatible';
    const acceptsCredential = credential.required || isCustom;
    const credentialState = !acceptsCredential ? '无需 API Key' : credential.api_key ? '待保存' : credential.configured ? 'API Key 已配置' : '尚未配置 API Key';
    const result = testResults[role];
    const currentResult = result?.fingerprint === fingerprint(value, role) ? result : undefined;
    const testingCurrent = testingRole === role && testingFingerprint === fingerprint(value, role);
    const resultLabel = currentResult && (currentResult.message.startsWith(currentResult.success ? '连接成功' : '连接失败')
      ? currentResult.message : `${currentResult.success ? '连接成功' : '连接失败'}：${currentResult.message}`);
    return <div className="welcome-connection-role">
      <div className="welcome-provider-row">
        <span className="welcome-field-caption">{title} · 服务商</span>
        <ScrollableSelect compact ariaLabel={`${title}服务商`} className="welcome-provider-select" value={selected.provider} options={providers.map((provider) => ({ value: provider.id, label: guidedProviderLabels[provider.id] || provider.label }))}
          // The handler reads remembered provider state only when the user selects an option.
          // eslint-disable-next-line react-hooks/refs
          onChange={(providerId) => selectProvider(role, providerId)} />
      </div>
      <div className="welcome-connection-fields">
        <div className="welcome-model-field"><ModelPicker role={role} title={title} model={selected.model} displayName={selected.display_name || ''} models={models} guided onChange={(model, displayName) => updateModel(role, model, displayName)} /></div>
        {cannotSeeImages && <p className="welcome-capability-warning" role="alert">该模型不支持多模态，请更换模型。</p>}
        {unknownVision && <p className="welcome-credential-state">此模型的识图能力尚未确认，可用下方测试检查。</p>}
        {isCustom && <div className="welcome-field"><label htmlFor={`${role}-guided-base-url`}>Base URL</label><input id={`${role}-guided-base-url`} className={controlClass} value={value.endpoints[role].base_url} onChange={(event) => updateEndpoint(role, event.target.value)} placeholder="https://example.com/v1" autoComplete="url" spellCheck={false} /></div>}
        {acceptsCredential ? <div className="welcome-field"><label htmlFor={`${role}-guided-api-key`}>API Key</label><input id={`${role}-guided-api-key`} className={controlClass} type="password" autoComplete="new-password" value={credential.api_key || ''} onChange={(event) => updateCredential(role, event.target.value)} placeholder={credential.configured ? '留空保留现有密钥' : '填写 API Key'} /><p role="status" className="welcome-credential-state">{credentialState}</p></div> : <p className="welcome-credential-state" role="status">{credentialState}</p>}
        <div className="welcome-connection-check"><span role="status" className={currentResult ? (currentResult.success ? 'is-success' : 'is-error') : ''}>{testingCurrent ? '正在测试连接…' : resultLabel || '连接尚未测试'}</span><button type="button" className="app-ghost-button" onClick={() => void testConnection(role)} disabled={testingRole !== null || !selected.model.trim() || cannotSeeImages}>{testingCurrent ? <LoaderCircle size={15} className="animate-spin" /> : <Link2 size={15} />}{role === 'vision' ? '测试识图能力' : '测试文字连接'}</button></div>
      </div>
    </div>;
  };

  const connectionEditor = <div className="settings-model-manager welcome-connection-panel">
    <div className="welcome-mode-switch" role="group" aria-label="模型配置方式">
      <button type="button" aria-pressed={value.multimodal_mode === 'native'} className={value.multimodal_mode === 'native' ? 'is-selected' : ''} onClick={() => changeGuidedMode('native')}><strong>单模型</strong><span>一个模型处理文字与图片</span></button>
      <button type="button" aria-pressed={value.multimodal_mode === 'split'} className={value.multimodal_mode === 'split' ? 'is-selected' : ''} onClick={() => changeGuidedMode('split')}><strong>双模型</strong><span>回答和识图分别配置</span></button>
    </div>
    <div className={`welcome-role-grid ${value.multimodal_mode === 'split' ? 'is-split' : ''}`}>
      {renderGuidedRole(reasoningRole, '回答模型')}
      {value.multimodal_mode === 'split' && renderGuidedRole('vision', '识图模型')}
    </div>
    <section className="welcome-advanced"><button type="button" className="app-ghost-button welcome-advanced-toggle" aria-expanded={connectionExpanded} aria-controls="welcome-advanced-fields" onClick={() => setConnectionsOpen((open) => !open)}><ChevronDown size={15} className={connectionExpanded ? 'rotate-180' : ''} />高级配置</button>
      {connectionExpanded && <div id="welcome-advanced-fields" className="welcome-advanced-fields">
        {connectedRoles.filter((role) => value.roles[role].provider !== 'openai_compatible').map((role) => <div className="welcome-field" key={role}><label htmlFor={`${role}-guided-override-url`}>{role === reasoningRole ? '回答模型' : '独立视觉模型'} Base URL</label><input id={`${role}-guided-override-url`} className={controlClass} value={value.endpoints[role].base_url} onChange={(event) => updateEndpoint(role, event.target.value)} placeholder="https://example.com/v1" autoComplete="url" spellCheck={false} /></div>)}
      </div>}
    </section>
  </div>;

  if (guided) return connectionEditor;

  return (
    <div className="settings-model-manager">
      {!guided && <section aria-labelledby="profile-heading" className="settings-section">
        <h4 id="profile-heading" className="settings-section-title">当前方案与方案管理</h4><p className="settings-secondary">选择其他方案会立即切换并应用。</p>
        <div className={fieldRowClass}>
          <span className="settings-label">方案</span>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
            <ScrollableSelect
              compact
              ariaLabel="切换并应用模型方案"
              className="min-w-0 flex-1"
              value={profileSelectValue}
              options={[
                ...(!editingSavedProfile ? [{ value: '__draft__', label: '新方案', description: '未保存' }] : []),
                ...profiles.map((profile) => ({ value: profile.id, label: profile.name, description: profile.id === value.active_profile_id ? '当前生效' : undefined })),
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
      </section>}

      {connectionEditor}
    </div>
  );
}

function ModelPicker({ role, title, model, displayName, models, onChange, guided = false }: { role: ModelRoleId; title: string; model: string; displayName: string; models: ModelSettingsValue['models']; onChange: (model: string, displayName?: string) => void; guided?: boolean }) {
  const isSuggested = models.some((item) => item.id === model);
  const options = [
    ...models.map((item) => ({ value: item.id, label: item.label, description: item.label === item.id ? undefined : item.id })),
    ...(!isSuggested ? [{ value: '__current_custom__', label: displayName || model || '未命名自定义模型', description: model || '等待填写 Model ID' }] : []),
    { value: '__new_custom__', label: '添加自定义模型…' },
  ];
  return (
    <>
      <div className={fieldRowClass}>
        <span className="settings-label">{guided ? '模型' : 'Model'}</span>
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
