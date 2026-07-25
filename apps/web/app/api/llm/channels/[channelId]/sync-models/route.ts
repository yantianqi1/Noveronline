import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

/**
 * BFF proxy → Go control plane `POST /v1/llm/channels/{channelId}/sync-models`.
 * Pulls the provider's live model catalog into the channel so the binding
 * pickers have real model ids to offer.
 */
export async function POST(
  request: Request,
  context: { params: Promise<{ channelId: string }> },
) {
  const tenantId = tenantFrom(request);
  if (!tenantId) {
    return missingTenantResponse();
  }
  const { channelId } = await context.params;

  try {
    const result = await proxyToApi({
      path: `/v1/llm/channels/${encodeURIComponent(channelId)}/sync-models`,
      method: "POST",
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
