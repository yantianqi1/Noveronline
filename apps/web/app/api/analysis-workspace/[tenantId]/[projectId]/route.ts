import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Client-reachable workspace file preview for Overview analysis modal.
 * Avoids full RSC remount when switching files inside the dialog.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ tenantId: string; projectId: string }> },
) {
  const { tenantId } = await params;
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  if (!sessionCookie) {
    return failure("UNAUTHENTICATED", 401);
  }

  const query = new URL(request.url).searchParams;
  const runId = query.get("runId")?.trim() ?? "";
  const path = query.get("path")?.trim() ?? "";
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(runId)) {
    return failure("VALIDATION_FAILED", 400);
  }
  if (!path || path.includes("..") || path.startsWith("/") || path.length > 512) {
    return failure("VALIDATION_FAILED", 400);
  }

  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  const upstream = `${process.env.MIROFISH_API_BASE_URL ?? "http://127.0.0.1:3888"}/v1/analysis-runs/${encodeURIComponent(runId)}/workspace/files/${encodedPath}`;
  const response = await fetch(upstream, {
    headers: {
      Cookie: `mirofish_session=${sessionCookie}`,
      "X-Tenant-Id": tenantId,
    },
    cache: "no-store",
  }).catch(() => null);

  if (!response) {
    return failure("ANALYSIS_WORKSPACE_QUERY_FAILED", 502);
  }

  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok || !payload) {
    const error = (payload?.error ?? {}) as { code?: string };
    return failure(error.code || "ANALYSIS_WORKSPACE_QUERY_FAILED", response.status || 502);
  }

  return NextResponse.json(
    { ok: true, ...payload },
    { headers: { "Cache-Control": "private, no-store" } },
  );
}

function failure(code: string, status: number) {
  return NextResponse.json({ ok: false, code, message: code }, { status });
}
