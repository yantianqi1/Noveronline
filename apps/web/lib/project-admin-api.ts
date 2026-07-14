export type ProjectAdminFailure = { ok: false; code: string; message: string; request_id: string };
export type ProjectAdminContext = { tenantId: string; sessionCookie?: string; csrfToken?: string };
export type AdminProject = { tenant_id: string; project_id: string; title: string; status: string; role: string };

export async function createProject(
  input: ProjectAdminContext & { title: string },
): Promise<{ ok: true; project: AdminProject } | ProjectAdminFailure> {
  return request(`/v1/tenants/${encodeURIComponent(input.tenantId)}/projects`, input, {
    method: "POST",
    body: JSON.stringify({ title: input.title }),
  });
}

export async function renameProject(
  input: ProjectAdminContext & { projectId: string; title: string },
): Promise<{ ok: true; project: AdminProject } | ProjectAdminFailure> {
  return request(`/v1/tenants/${encodeURIComponent(input.tenantId)}/projects/${encodeURIComponent(input.projectId)}`, input, {
    method: "PATCH",
    body: JSON.stringify({ title: input.title }),
  });
}

async function request<T>(
  path: string,
  input: { sessionCookie?: string; csrfToken?: string },
  init: RequestInit = {},
): Promise<T | ProjectAdminFailure> {
  try {
    const headers: Record<string, string> = {};
    if (init.body) headers["Content-Type"] = "application/json";
    if (input.sessionCookie) headers.Cookie = `mirofish_session=${input.sessionCookie}`;
    if (input.csrfToken) headers["X-CSRF-Token"] = input.csrfToken;
    const response = await fetch(`${apiBase()}${path}`, { ...init, headers: { ...headers, ...init.headers }, cache: "no-store" });
    const payload = (await response.json()) as Record<string, unknown>;
    if (response.ok) return payload as T;
    const error = (payload.error ?? {}) as Record<string, unknown>;
    return {
      ok: false,
      code: stringValue(error.code) || "PROJECT_ADMIN_REQUEST_FAILED",
      message: stringValue(error.message) || `HTTP ${response.status}`,
      request_id: stringValue(error.request_id),
    };
  } catch (error) {
    return {
      ok: false,
      code: "PROJECT_ADMIN_REQUEST_FAILED",
      message: error instanceof Error ? error.message : "network request failed",
      request_id: "",
    };
  }
}

function apiBase() {
  return (process.env.MIROFISH_API_BASE_URL ?? "http://localhost:8080").replace(/\/$/, "");
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}
