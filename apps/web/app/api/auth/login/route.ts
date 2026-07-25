import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

/**
 * BFF proxy → Go control plane `POST /v1/auth/login`.
 *
 * The browser only ever talks to this same-origin Next route. The shared
 * proxy forwards the credentials, attaches the server-signed trusted-client
 * proof (the secret stays server-side), and relays the `mirofish_session`
 * cookie back so the session is established on our own origin.
 */
export async function POST(request: Request) {
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
    const result = await proxyToApi({ path: "/v1/auth/login", method: "POST", body, request });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
