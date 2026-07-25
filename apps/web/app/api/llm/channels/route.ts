import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

/**
 * BFF proxy → Go control plane `POST /v1/llm/channels`.
 *
 * Creates a tenant-scoped LLM channel. The API key is sent to Go, which
 * encrypts it at rest; the key never persists in the browser beyond the form.
 * Channel management is tenant-scoped (not project-scoped), so this route lives
 * outside the project catch-all and only needs the tenant context header.
 */
export async function POST(request: Request) {
  const tenantId = tenantFrom(request);
  if (!tenantId) {
    return missingTenantResponse();
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
    const result = await proxyToApi({ path: "/v1/llm/channels", method: "POST", body, request, tenantId });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
