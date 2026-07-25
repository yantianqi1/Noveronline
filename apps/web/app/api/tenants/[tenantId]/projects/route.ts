import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

/**
 * BFF proxy → Go `POST /v1/tenants/{tenantId}/projects`.
 *
 * Creates a novel (project) inside a tenant. The actor must be a tenant owner
 * or admin; CSRF and session cookies are forwarded by proxyToApi.
 */
export async function POST(
  request: Request,
  context: { params: Promise<{ tenantId: string }> },
) {
  const { tenantId: rawTenantId } = await context.params;
  const tenantId = rawTenantId?.trim();
  if (!tenantId) {
    return Response.json(
      { error: { code: "VALIDATION_FAILED", message: "缺少工作区" } },
      { status: 400 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { error: { code: "VALIDATION_FAILED", message: "请求格式不正确" } },
      { status: 400 },
    );
  }

  try {
    const result = await proxyToApi({
      path: `/v1/tenants/${encodeURIComponent(tenantId)}/projects`,
      method: "POST",
      body,
      request,
      tenantId,
    });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
