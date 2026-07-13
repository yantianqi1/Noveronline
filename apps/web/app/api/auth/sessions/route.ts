import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getCurrentUserSessions } from "../../../../lib/api";

export async function GET() {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  if (!sessionCookie) {
    return sessionResponse({
      ok: false,
      code: "UNAUTHENTICATED",
      message: "user context is required",
      request_id: "",
    }, 401);
  }

  const result = await getCurrentUserSessions({ sessionCookie });
  return sessionResponse(result, result.ok ? 200 : statusForSessionFailure(result.code));
}

function sessionResponse(payload: unknown, status: number) {
  const response = NextResponse.json(payload, { status });
  response.headers.set("cache-control", "private, no-store");
  return response;
}

function statusForSessionFailure(code: string) {
  if (code === "UNAUTHENTICATED") return 401;
  if (code === "AUTH_ACCESS_DENIED") return 403;
  if (code === "AUTH_BACKEND_UNCONFIGURED") return 503;
  return 502;
}
