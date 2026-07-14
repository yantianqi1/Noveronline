import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Client-reachable analysis event source for Overview step log.
 * Supports JSON poll (default) and held-open SSE when stream=1.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ tenantId: string; projectId: string }> },
) {
  const { tenantId } = await params;
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  if (!sessionCookie) {
    return eventsFailure("UNAUTHENTICATED", 401);
  }
  const query = new URL(request.url).searchParams;
  const runId = query.get("runId")?.trim() ?? "";
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(runId)) {
    return eventsFailure("VALIDATION_FAILED", 400);
  }
  const afterEventId = query.get("after_event_id")?.trim() ?? "";
  if (afterEventId && !/^[A-Za-z0-9_-]{1,128}$/.test(afterEventId)) {
    return eventsFailure("VALIDATION_FAILED", 400);
  }
  const stream = query.get("stream") === "1";

  const upstream = new URL(
    `${process.env.MIROFISH_API_BASE_URL ?? "http://127.0.0.1:3888"}/v1/analysis-runs/${encodeURIComponent(runId)}/events`,
  );
  if (afterEventId) {
    upstream.searchParams.set("after_event_id", afterEventId);
  }
  if (stream) {
    upstream.searchParams.set("stream", "1");
  }

  const headers: Record<string, string> = {
    Cookie: `mirofish_session=${sessionCookie}`,
    "X-Tenant-Id": tenantId,
  };
  if (stream) {
    headers.Accept = "text/event-stream";
    if (afterEventId) {
      headers["Last-Event-ID"] = afterEventId;
    }
  }

  const response = await fetch(upstream, {
    headers,
    cache: "no-store",
  }).catch(() => null);
  if (!response) {
    return eventsFailure("ANALYSIS_EVENTS_QUERY_FAILED", 502);
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { error?: { code?: string } } | null;
    const code = payload?.error?.code ?? "ANALYSIS_EVENTS_QUERY_FAILED";
    return eventsFailure(publicEventsCode(code), statusForEventsFailure(code));
  }

  if (stream) {
    return new Response(response.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "private, no-store",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  }

  const payload = (await response.json().catch(() => null)) as { items?: unknown } | null;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  return NextResponse.json(
    { ok: true, run_id: runId, after_event_id: afterEventId, items },
    { headers: { "Cache-Control": "private, no-store" } },
  );
}

function eventsFailure(code: string, status: number) {
  return NextResponse.json({ ok: false, code, message: "analysis events query failed" }, { status });
}

function publicEventsCode(code: string) {
  switch (code) {
    case "UNAUTHENTICATED":
    case "AUTH_ACCESS_DENIED":
    case "NOT_FOUND":
    case "ANALYSIS_RUN_NOT_FOUND":
      return code;
    default:
      return "ANALYSIS_EVENTS_QUERY_FAILED";
  }
}

function statusForEventsFailure(code: string) {
  switch (code) {
    case "UNAUTHENTICATED":
      return 401;
    case "AUTH_ACCESS_DENIED":
      return 403;
    case "NOT_FOUND":
    case "ANALYSIS_RUN_NOT_FOUND":
      return 404;
    default:
      return 502;
  }
}
