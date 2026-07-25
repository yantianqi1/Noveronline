import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

/**
 * BFF proxy → Go control plane `GET /v1/me`.
 * Returns the CurrentUser envelope: user, active_tenants, active_projects.
 * The browser never sees the session cookie logic — we forward it server-side.
 */
export async function GET(request: Request) {
  try {
    const result = await proxyToApi({ path: "/v1/me", method: "GET", request });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
