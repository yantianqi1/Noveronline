/**
 * Browser client for tenant-scoped novel (project) administration.
 * Mutations go through same-origin BFF routes with CSRF + X-Tenant-Id.
 */

export type CreatedProject = {
  tenant_id: string;
  project_id: string;
  title: string;
  status: string;
  role: string;
};

export class ProjectAdminError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ProjectAdminError";
  }
}

async function readError(response: Response): Promise<ProjectAdminError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as {
      error?: { code?: string; message?: string };
      ok?: boolean;
    };
    code = payload?.error?.code;
    if (payload?.error?.message) {
      message = payload.error.message;
    }
  } catch {
    // non-JSON body — keep the generic message
  }
  return new ProjectAdminError(message, code, response.status);
}

/** Create a novel in the given tenant. Requires tenant owner/admin. */
export async function createProject(
  tenantId: string,
  csrfToken: string,
  title: string,
): Promise<CreatedProject> {
  const response = await fetch(`/api/tenants/${encodeURIComponent(tenantId)}/projects`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw await readError(response);
  }
  const payload = (await response.json()) as { ok?: boolean; project?: CreatedProject };
  if (!payload.project?.project_id) {
    throw new ProjectAdminError("创建成功但未返回作品信息", "INVALID_RESPONSE", response.status);
  }
  return payload.project;
}
