import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

/**
 * BFF proxy → Go control plane `POST /v1/auth/signup`.
 * The control plane keeps this route explicitly disabled in the current
 * invite/admin-provisioned release; retaining the proxy keeps the response
 * contract uniform if self-service signup is enabled in a later release.
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
    const result = await proxyToApi({ path: "/v1/auth/signup", method: "POST", body, request });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
