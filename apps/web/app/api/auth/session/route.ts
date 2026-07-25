import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

/**
 * BFF proxy → Go control plane `DELETE /v1/auth/session` (logout).
 *
 * The Go API requires a valid `X-CSRF-Token` on this cookie-authenticated
 * mutation; the shared proxy forwards whatever the client echoed. On success
 * upstream replies 204 and clears the `mirofish_session` cookie, which we
 * relay back to the browser.
 */
export async function DELETE(request: Request) {
  try {
    const result = await proxyToApi({
      path: "/v1/auth/session",
      method: "DELETE",
      request,
    });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
