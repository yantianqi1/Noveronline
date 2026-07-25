import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

/**
 * BFF proxy → Go `PUT /v1/uploads/{uploadId}/object` (step 2 of upload).
 * Streams the raw file bytes to object storage via the Go API. Content-Type is
 * the source file's MIME type, forwarded so the API can validate it.
 */
export async function PUT(
  request: Request,
  context: { params: Promise<{ uploadId: string }> },
) {
  const { uploadId } = await context.params;
  const tenantId = tenantFrom(request);
  if (!tenantId) {
    return missingTenantResponse();
  }

  const rawBody = await request.arrayBuffer();
  const contentType = request.headers.get("Content-Type") ?? "application/octet-stream";

  try {
    const result = await proxyToApi({
      path: `/v1/uploads/${encodeURIComponent(uploadId)}/object`,
      method: "PUT",
      rawBody,
      contentType,
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
