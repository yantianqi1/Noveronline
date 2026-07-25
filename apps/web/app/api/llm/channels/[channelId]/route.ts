import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

/**
 * BFF proxy → Go control plane `/v1/llm/channels/{channelId}` (PATCH / DELETE).
 *
 * Updates a tenant channel (rename, rotate the API key, toggle, concurrency)
 * or disables it. Tenant-scoped like channel creation; only the tenant context
 * header is required.
 */
async function handle(request: Request, context: { params: Promise<{ channelId: string }> }) {
  const tenantId = tenantFrom(request);
  if (!tenantId) {
    return missingTenantResponse();
  }
  const { channelId } = await context.params;
  const method = request.method.toUpperCase();
  if (method !== "PATCH" && method !== "DELETE") {
    return Response.json({ error: { code: "NOT_FOUND", message: "未知的渠道接口" } }, { status: 404 });
  }

  let body: unknown;
  if (method === "PATCH") {
    try {
      body = await request.json();
    } catch {
      return Response.json(
        { error: { code: "VALIDATION_FAILED", message: "请求格式不正确" } },
        { status: 400 },
      );
    }
  }

  try {
    const result = await proxyToApi({
      path: `/v1/llm/channels/${encodeURIComponent(channelId)}`,
      method,
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

export const PATCH = handle;
export const DELETE = handle;
