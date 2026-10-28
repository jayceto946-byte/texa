export type ModelRoleId = 'reasoning' | 'vision';

export type ProviderCatalogItem = {
  id: string;
  label: string;
  capabilities: string[];
  default_endpoint: string;
  default_models: Partial<Record<ModelRoleId, string>>;
  requires_api_key: boolean;
};

export type ModelRoleValue = {
  provider: string;
  model: string;
  display_name?: string;
  credential_id: string;
  endpoint_id: string;
};

export type ModelSettingsValue = {
  providers: ProviderCatalogItem[];
  models: Array<{ provider: string; id: string; label: string; capabilities: string[] }>;
  roles: Record<ModelRoleId, ModelRoleValue>;
  credentials: Record<ModelRoleId, { configured: boolean; required: boolean; api_key?: string; value?: string }>;
  endpoints: Record<ModelRoleId, { base_url: string; is_default: boolean }>;
  multimodal_mode: 'split' | 'native';
  profiles?: Array<{ id: string; name: string; roles: Record<ModelRoleId, ModelRoleValue>; endpoints: Record<ModelRoleId, { base_url: string; is_default: boolean }>; multimodal_mode: 'split' | 'native' }>;
  active_profile_id?: string;
  editing_profile_id?: string;
  profile_name?: string;
  credential_status?: Record<string, boolean>;
};
