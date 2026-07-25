import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

/**
 * BFF proxy → Go `POST /v1/uploads/{uploadId}/complete` (step 3 of upload).
 * Finalizes the source file so it can be used to start a Seed run.
 */
export async function POST(
  request: Request,
  context: { params: Promise<{ uploadId: string }> },
) {
  const { uploadId } = await context.params;
  const tenantId = tenantFrom(request);
  if (!tenantId) {
    return missingTenantResponse();
  }

  try {
    const result = await proxyToApi({
      path: `/v1/uploads/${encodeURIComponent(uploadId)}/complete`,
      method: "POST",
      body: {},
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
