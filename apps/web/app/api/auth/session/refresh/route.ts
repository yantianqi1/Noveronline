import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getSessionCSRFToken, rotateCurrentSession } from "../../../../../lib/api";

export async function POST() {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  if (!sessionCookie) {
    return sessionRefreshFailure("UNAUTHENTICATED", "");
  }

  const csrfResult = await getSessionCSRFToken({ sessionCookie });
  if (!csrfResult.ok) {
    return sessionRefreshFailure(csrfResult.code, csrfResult.request_id);
  }

  const rotationResult = await rotateCurrentSession({ sessionCookie, csrfToken: csrfResult.csrf_token });
  if (!rotationResult.ok) {
    return sessionRefreshFailure(rotationResult.code, rotationResult.request_id);
  }

  const response = new NextResponse(null, { status: 204 });
  response.cookies.set("mirofish_session", rotationResult.session_cookie.value, {
    httpOnly: rotationResult.session_cookie.http_only,
    maxAge: rotationResult.session_cookie.max_age,
    path: rotationResult.session_cookie.path,
    sameSite: rotationResult.session_cookie.same_site,
    secure: rotationResult.session_cookie.secure,
  });
  return response;
}

function sessionRefreshFailure(code: string, requestId: string) {
  return NextResponse.json(
    {
      ok: false,
      code: code || "SESSION_REFRESH_FAILED",
      message: "session refresh failed",
      request_id: requestId || "",
    },
    { status: statusForRefreshFailure(code) },
  );
}

function statusForRefreshFailure(code: string) {
  if (code === "UNAUTHENTICATED") {
    return 401;
  }
  if (code === "AUTH_ACCESS_DENIED") {
    return 403;
  }
  if (code === "AUTH_BACKEND_UNCONFIGURED") {
    return 503;
  }
  return 502;
}
