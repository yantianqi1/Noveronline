import type {
  ListResponse,
  LLMChannel,
  LLMModel,
  LLMModule,
  LLMModuleBinding,
} from "@/lib/api/llm-types";

/**
 * Browser-side client for the LLM settings workbench. All calls go to
 * same-origin BFF routes; the browser supplies the tenant via X-Tenant-Id
 * (from the shelf's project selection) and a CSRF token for mutations.
 */

export class LLMError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "LLMError";
  }
}

async function readError(response: Response): Promise<LLMError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // keep generic message
  }
  return new LLMError(message, code, response.status);
}

async function getJson<T>(path: string, tenantId: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json", "X-Tenant-Id": tenantId },
    cache: "no-store",
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

async function sendJson<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  tenantId: string,
  csrfToken: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

// ── Reads ────────────────────────────────────────────────────────────────

export async function fetchLLMModules(projectId: string, tenantId: string): Promise<LLMModule[]> {
  const data = await getJson<ListResponse<LLMModule>>(
    `/api/projects/${projectId}/llm/modules`,
    tenantId,
  );
  return data.items ?? [];
}

export async function fetchLLMBindings(
  projectId: string,
  tenantId: string,
): Promise<LLMModuleBinding[]> {
  const data = await getJson<ListResponse<LLMModuleBinding>>(
    `/api/projects/${projectId}/llm/module-bindings`,
    tenantId,
  );
  return data.items ?? [];
}

export async function fetchLLMChannels(projectId: string, tenantId: string): Promise<LLMChannel[]> {
  const data = await getJson<ListResponse<LLMChannel>>(
    `/api/projects/${projectId}/llm/channels`,
    tenantId,
  );
  return data.items ?? [];
}

export async function fetchLLMModels(
  projectId: string,
  tenantId: string,
  channelId: string,
): Promise<LLMModel[]> {
  const data = await getJson<ListResponse<LLMModel>>(
    `/api/projects/${projectId}/llm/channels/${encodeURIComponent(channelId)}/models`,
    tenantId,
  );
  return data.items ?? [];
}

// ── Mutations ────────────────────────────────────────────────────────────

export function upsertModuleBinding(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  moduleKey: string,
  input: { channel_id: string; model_id: string; settings?: Record<string, unknown> },
) {
  return sendJson<LLMModuleBinding>(
    "PUT",
    `/api/projects/${projectId}/llm/module-bindings/${encodeURIComponent(moduleKey)}`,
    tenantId,
    csrfToken,
    { channel_id: input.channel_id, model_id: input.model_id, settings: input.settings ?? {} },
  );
}

export function deleteModuleBinding(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  moduleKey: string,
) {
  return sendJson<LLMModuleBinding>(
    "DELETE",
    `/api/projects/${projectId}/llm/module-bindings/${encodeURIComponent(moduleKey)}`,
    tenantId,
    csrfToken,
  );
}

export type CreateChannelInput = {
  name: string;
  provider: string;
  base_url: string;
  api_key: string;
  max_concurrency: number;
  external_provider_opt_in: boolean;
};

export function createLLMChannel(
  tenantId: string,
  csrfToken: string,
  input: CreateChannelInput,
) {
  return sendJson<LLMChannel>("POST", `/api/llm/channels`, tenantId, csrfToken, input);
}

export type UpdateChannelInput = {
  name: string;
  base_url: string;
  /** Optional — only sent when rotating the key. Empty means "keep current". */
  api_key?: string;
  max_concurrency: number;
  external_provider_opt_in: boolean;
  enabled: boolean;
};

export function updateLLMChannel(
  tenantId: string,
  csrfToken: string,
  channelId: string,
  input: UpdateChannelInput,
) {
  return sendJson<LLMChannel>(
    "PATCH",
    `/api/llm/channels/${encodeURIComponent(channelId)}`,
    tenantId,
    csrfToken,
    input,
  );
}

export function syncLLMChannelModels(tenantId: string, csrfToken: string, channelId: string) {
  return sendJson<{ synced?: number }>(
    "POST",
    `/api/llm/channels/${encodeURIComponent(channelId)}/sync-models`,
    tenantId,
    csrfToken,
  );
}
