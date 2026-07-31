import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

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
    const result = await proxyToApi({
      path: "/v1/collaboration/invitations/accept",
      method: "POST",
      body,
      request,
    });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) return upstreamUnavailableResponse();
    throw error;
  }
}
