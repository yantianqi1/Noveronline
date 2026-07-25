import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

/**
 * BFF proxy → Go control plane `GET /v1/auth/csrf-token`.
 * Requires an active session; returns `{ csrf_token }` which the client must
 * echo back as `X-CSRF-Token` on any mutating (cookie-authenticated) call.
 */
export async function GET(request: Request) {
  try {
    const result = await proxyToApi({ path: "/v1/auth/csrf-token", method: "GET", request });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
