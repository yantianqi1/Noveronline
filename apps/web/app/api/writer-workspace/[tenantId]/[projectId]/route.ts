import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Client-reachable read proxy for writer workspace data.
 *
 * Lets browser components (TOC rail, manuscript flow) hydrate chapter/scene/
 * block content without a full page navigation, which eliminates the visible
 * flicker that form-GET navigation caused on every click. Read-only (GET) —
 * mutations still go through server actions. Backend remains the authority;
 * we forward the session cookie + tenant and surface only sanitized failures.
 *
 * Query params:
 *   resource=chapters | scenes | blocks | block | versions
 *   chapterId=<id>        (for scenes)
 *   blockId=<id>          (for block / versions)
 *   includeDeleted=1      (optional, for blocks)
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ tenantId: string; projectId: string }> },
) {
  const { tenantId, projectId } = await params;
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  if (!sessionCookie) {
    return workspaceFailure("UNAUTHENTICATED", 401);
  }
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(projectId)) {
    return workspaceFailure("VALIDATION_FAILED", 400);
  }

  const query = new URL(request.url).searchParams;
  const resource = query.get("resource") ?? "";
  const base = process.env.MIROFISH_API_BASE_URL ?? "http://127.0.0.1:3888";
  const projectPath = `/v1/projects/${encodeURIComponent(projectId)}`;
  const manuscriptPath = `${projectPath}/manuscript-workspace`;

  let upstreamPath: string;
  switch (resource) {
    case "chapters":
      upstreamPath = `${projectPath}/chapters`;
      break;
    case "scenes": {
      const chapterId = query.get("chapterId")?.trim() ?? "";
      if (!/^[A-Za-z0-9_-]{1,128}$/.test(chapterId)) {
        return workspaceFailure("VALIDATION_FAILED", 400);
      }
      upstreamPath = `/v1/chapters/${encodeURIComponent(chapterId)}/scenes`;
      break;
    }
    case "blocks": {
      const includeDeleted = query.get("includeDeleted") === "1" || query.get("includeDeleted") === "true";
      upstreamPath = `${manuscriptPath}/blocks${includeDeleted ? "?include_deleted=true" : ""}`;
      break;
    }
    case "block": {
      const blockId = query.get("blockId")?.trim() ?? "";
      if (!/^[A-Za-z0-9_-]{1,128}$/.test(blockId)) {
        return workspaceFailure("VALIDATION_FAILED", 400);
      }
      upstreamPath = `${manuscriptPath}/blocks/${encodeURIComponent(blockId)}`;
      break;
    }
    case "versions": {
      const blockId = query.get("blockId")?.trim() ?? "";
      if (!/^[A-Za-z0-9_-]{1,128}$/.test(blockId)) {
        return workspaceFailure("VALIDATION_FAILED", 400);
      }
      upstreamPath = `${manuscriptPath}/blocks/${encodeURIComponent(blockId)}/versions`;
      break;
    }
    default:
      return workspaceFailure("VALIDATION_FAILED", 400);
  }

  const response = await fetch(`${base}${upstreamPath}`, {
    headers: {
      Accept: "application/json",
      Cookie: `mirofish_session=${sessionCookie}`,
      "X-Tenant-Id": tenantId,
    },
    cache: "no-store",
  }).catch(() => null);

  if (!response) {
    return workspaceFailure("WRITER_WORKSPACE_UNAVAILABLE", 502);
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const code = readErrorCode(payload) ?? "WRITER_WORKSPACE_UNAVAILABLE";
    return workspaceFailure(publicCode(code), statusFor(code));
  }

  return NextResponse.json(
    { ok: true, resource, data: payload },
    { headers: { "Cache-Control": "private, no-store" } },
  );
}

function readErrorCode(payload: unknown): string | null {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    const error = (payload as { error?: { code?: unknown } }).error;
    if (error && typeof error.code === "string") return error.code;
  }
  return null;
}

function publicCode(code: string) {
  switch (code) {
    case "UNAUTHENTICATED":
    case "AUTH_ACCESS_DENIED":
    case "NOT_FOUND":
    case "HTTP_404":
      return code === "HTTP_404" ? "NOT_FOUND" : code;
    default:
      return "WRITER_WORKSPACE_UNAVAILABLE";
  }
}

function statusFor(code: string) {
  switch (code) {
    case "UNAUTHENTICATED":
      return 401;
    case "AUTH_ACCESS_DENIED":
      return 403;
    case "NOT_FOUND":
    case "HTTP_404":
      return 404;
    default:
      return 502;
  }
}

function workspaceFailure(code: string, status: number) {
  return NextResponse.json({ ok: false, code, message: "writer workspace read failed" }, { status });
}
