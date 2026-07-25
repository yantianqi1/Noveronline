import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

/**
 * BFF proxy → Go `POST /v1/projects/{projectId}/uploads` (step 1 of upload).
 * Creates the source-file record and returns { upload_id, ... }. The browser
 * then PUTs the raw bytes to /api/uploads/{uploadId}/object and completes.
 */
export async function POST(
  request: Request,
  context: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await context.params;
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
    const result = await proxyToApi({
      path: `/v1/projects/${encodeURIComponent(projectId)}/uploads`,
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
