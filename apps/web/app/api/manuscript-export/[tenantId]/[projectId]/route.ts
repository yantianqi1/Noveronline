import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createHash } from "node:crypto";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ tenantId: string; projectId: string }> },
) {
  const { tenantId, projectId } = await params;
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  if (!sessionCookie) {
    return artifactFailure("UNAUTHENTICATED", "", 401);
  }
  const exportId = new URL(request.url).searchParams.get("exportId")?.trim() ?? "";
  if (!/^[A-Za-z0-9-]{8,128}$/.test(exportId)) {
    return artifactFailure("VALIDATION_FAILED", "", 400);
  }
  const upstream = await fetch(
    `${process.env.MIROFISH_API_BASE_URL ?? "http://127.0.0.1:3888"}/v1/projects/${encodeURIComponent(projectId)}/manuscript/exports/${encodeURIComponent(exportId)}/download`,
    { headers: { Cookie: `mirofish_session=${sessionCookie}`, "X-Tenant-Id": tenantId }, cache: "no-store" },
  ).catch(() => null);
  if (!upstream) return artifactFailure("MANUSCRIPT_EXPORT_FAILED", "", 502);
  if (!upstream.ok) {
    const payload = await upstream.json().catch(() => null) as { error?: { code?: string }; request_id?: string } | null;
    const code = payload?.error?.code ?? "MANUSCRIPT_EXPORT_FAILED";
    return artifactFailure(code, payload?.request_id ?? "", statusForArtifactFailure(code));
  }
  const content = Buffer.from(await upstream.arrayBuffer());
  const sha256 = createHash("sha256").update(content).digest("hex");
  const expectedHash = upstream.headers.get("x-content-sha256")?.trim() ?? "";
  if (content.byteLength === 0 || (expectedHash && expectedHash !== sha256)) {
    return artifactFailure("MANUSCRIPT_EXPORT_ARTIFACT_INVALID", "", 502);
  }
  return new NextResponse(content, {
    status: 200,
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Disposition": `attachment; filename="manuscript-${exportId}.txt"`,
      "Content-Length": String(content.byteLength),
      "Content-Type": upstream.headers.get("content-type") ?? "text/plain; charset=utf-8",
      "X-Content-SHA256": sha256,
    },
  });
}

function artifactFailure(code: string, requestId: string, status: number) {
  return NextResponse.json(
    {
      ok: false,
      code: publicArtifactCode(code),
      message: "manuscript export failed",
      request_id: requestId || "",
    },
    { status },
  );
}

function publicArtifactCode(code: string) {
  switch (code) {
    case "UNAUTHENTICATED":
    case "AUTH_ACCESS_DENIED":
    case "MANUSCRIPT_EMPTY":
    case "MANUSCRIPT_EXPORT_NOT_READY":
    case "MANUSCRIPT_EXPORT_NOT_FOUND":
    case "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED":
      return code;
    default:
      return "MANUSCRIPT_EXPORT_FAILED";
  }
}

function statusForArtifactFailure(code: string) {
  switch (code) {
    case "UNAUTHENTICATED":
      return 401;
    case "AUTH_ACCESS_DENIED":
      return 403;
    case "MANUSCRIPT_EMPTY":
    case "MANUSCRIPT_EXPORT_NOT_READY":
      return 409;
    case "MANUSCRIPT_EXPORT_NOT_FOUND":
      return 404;
    case "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED":
      return 503;
    default:
      return 502;
  }
}
