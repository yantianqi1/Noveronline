import {
  proxyToApi,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/api-proxy";

/**
 * Shared helpers for project-scoped BFF routes.
 *
 * Every project data route needs the tenant context. The browser stores the
 * selected {tenant_id, project_id} after picking a project on the shelf and
 * echoes the tenant back as the `X-Tenant-Id` header; we forward it verbatim
 * to the Go API. We never invent or persist tenant scope server-side.
 */

export function tenantFrom(request: Request): string | null {
  const tenant = request.headers.get("X-Tenant-Id")?.trim();
  return tenant && tenant.length > 0 ? tenant : null;
}

export function missingTenantResponse(): Response {
  return Response.json(
    {
      error: {
        code: "TENANT_REQUIRED",
        message: "缺少工作区上下文，请返回书架重新进入项目",
      },
    },
    { status: 400 },
  );
}

export { proxyToApi, toResponse, upstreamUnavailableResponse, UpstreamUnavailableError };
