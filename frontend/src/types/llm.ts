export interface LlmChannel {
  channel_key: string;
  name: string;
  provider: string;
  base_url: string;
  api_base: string;
  api_key_masked: string;
  is_enabled: boolean;
  enabled: boolean;
  max_concurrency: number;
  models: LlmModel[];
  last_sync_status: string | null;
  last_sync_at: string | null;
  last_sync_error: string | null;
  runtime?: {
    inflight: number;
    waiting: number;
  };
  created_at: string;
}

export interface LlmModel {
  model_id: string;
  channel_key: string;
  display_name: string;
  context_window?: number;
  capabilities?: string[];
}

export interface LlmModule {
  module_key: string;
  label: string;
  description?: string;
  binding: LlmModuleBindingInfo | null;
}

export interface LlmModuleBindingInfo {
  channel_key: string;
  model_id: string;
}

export interface LlmModuleBinding {
  module_key: string;
  channel_key: string;
  model_id: string;
  display_name?: string;
  description?: string;
}

export interface LlmSettings {
  channels: LlmChannel[];
  modules: LlmModule[];
  module_bindings: LlmModuleBinding[];
  available_modules: AvailableModule[];
}

export interface AvailableModule {
  key: string;
  display_name: string;
  description: string;
  required: boolean;
}

export interface LlmActivity {
  calls: LlmActiveCall[];
  channels: Record<string, LlmChannelActivity>;
  total_active: number;
}

export interface LlmActiveCall {
  call_id: string;
  module: string;
  channel_key: string;
  model_id: string;
  started_at: string;
  elapsed_seconds: number;
}

export interface LlmChannelActivity {
  active_count: number;
  limit: number;
}
