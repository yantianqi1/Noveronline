/**
 * LLM settings domain types, mirroring the Go control-plane records in
 * apps/api/internal/llm. These are the exact JSON shapes the BFF relays back
 * from /v1/projects/{id}/llm/* and /v1/llm/*.
 */

export type LLMChannel = {
  channel_id: string;
  name: string;
  provider: string;
  base_url: string;
  max_concurrency: number;
  external_provider_opt_in: boolean;
  enabled: boolean;
  last_sync_at?: string;
  last_sync_status?: string;
  /** "tenant" | "platform" */
  scope: string;
  created_at: string;
  updated_at: string;
};

export type LLMModel = {
  model_id: string;
  owned_by?: string;
  context_window?: number;
  supports_tools: boolean;
  supports_json: boolean;
  input_cost?: number;
  output_cost?: number;
  created_at: string;
  updated_at: string;
};

export type LLMModule = {
  module_key: string;
  group: string;
  label: string;
  description: string;
};

export type LLMModuleBinding = {
  module_key: string;
  /** "project" | "tenant" | "platform" */
  scope: string;
  channel_id: string;
  channel_name: string;
  model_id: string;
  provider: string;
  base_url: string;
  supports_tools: boolean;
  supports_json: boolean;
  settings: Record<string, unknown>;
  updated_at: string;
};

export type ListResponse<T> = { items: T[] };
