import type {
  ListResponse,
  ProjectOverview,
  ReadinessSnapshot,
  SeedRun,
  SourceFile,
  WorkflowEvent,
} from "@/lib/api/overview-types";

/**
 * Browser-side client for the Overview workbench. All calls go to same-origin
 * BFF routes; the browser supplies the tenant via X-Tenant-Id (from the
 * project selection made on the shelf) and CSRF tokens for mutations.
 */

export class OverviewError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "OverviewError";
  }
}

/** The active project/tenant selection, persisted by the shelf. */
export type ProjectSelection = { tenant_id: string; project_id: string };

export function readProjectSelection(): ProjectSelection | null {
  try {
    const raw = window.sessionStorage.getItem("mirofish.activeProject");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ProjectSelection>;
    if (typeof parsed.tenant_id === "string" && typeof parsed.project_id === "string") {
      return { tenant_id: parsed.tenant_id, project_id: parsed.project_id };
    }
    return null;
  } catch {
    return null;
  }
}

async function readError(response: Response): Promise<OverviewError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // keep generic message
  }
  return new OverviewError(message, code, response.status);
}

async function getJson<T>(path: string, tenantId: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json", "X-Tenant-Id": tenantId },
    cache: "no-store",
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

async function postJson<T>(
  path: string,
  tenantId: string,
  csrfToken: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
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

export function fetchOverview(projectId: string, tenantId: string) {
  return getJson<ProjectOverview>(`/api/projects/${projectId}/overview`, tenantId);
}

export function fetchReadiness(projectId: string, tenantId: string) {
  return getJson<ReadinessSnapshot>(`/api/projects/${projectId}/readiness`, tenantId);
}

export async function fetchSourceFiles(projectId: string, tenantId: string): Promise<SourceFile[]> {
  const data = await getJson<ListResponse<SourceFile>>(
    `/api/projects/${projectId}/source-files`,
    tenantId,
  );
  return data.items ?? [];
}

export async function fetchSeedRuns(projectId: string, tenantId: string): Promise<SeedRun[]> {
  const data = await getJson<ListResponse<SeedRun>>(`/api/projects/${projectId}/seed-runs`, tenantId);
  return data.items ?? [];
}

export async function fetchSeedRunEvents(
  projectId: string,
  tenantId: string,
  runId: string,
  afterEventId?: string,
): Promise<WorkflowEvent[]> {
  const query = afterEventId ? `?after_event_id=${encodeURIComponent(afterEventId)}` : "";
  const data = await getJson<ListResponse<WorkflowEvent>>(
    `/api/projects/${projectId}/seed-runs/${runId}/events${query}`,
    tenantId,
  );
  return data.items ?? [];
}

// ── Mutations ────────────────────────────────────────────────────────────

export function startSeedRun(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  uploadId: string,
) {
  return postJson<{ run_id: string; status: string }>(
    `/api/projects/${projectId}/seed-runs`,
    tenantId,
    csrfToken,
    { upload_id: uploadId },
  );
}

export function cancelSeedRun(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  runId: string,
) {
  return postJson<{ run_id: string; status: string }>(
    `/api/projects/${projectId}/seed-runs/${runId}/cancel`,
    tenantId,
    csrfToken,
  );
}

export function retrySeedRun(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  runId: string,
) {
  return postJson<{ run_id: string; status: string }>(
    `/api/projects/${projectId}/seed-runs/${runId}/retry`,
    tenantId,
    csrfToken,
  );
}

/**
 * Delete one imported source file by upload id. The Go control plane returns
 * 204 No Content on success, so there's no JSON body to parse — we only
 * surface transport/API errors. Produced seed/graph data is intentionally kept.
 */
export async function deleteSourceFile(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  uploadId: string,
): Promise<void> {
  const response = await fetch(
    `/api/projects/${projectId}/source-files/${encodeURIComponent(uploadId)}`,
    {
      method: "DELETE",
      headers: {
        Accept: "application/json",
        "X-Tenant-Id": tenantId,
        "X-CSRF-Token": csrfToken,
      },
    },
  );
  if (!response.ok) throw await readError(response);
}
