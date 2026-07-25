import type { CurrentUser } from "@/lib/api/types";

/**
 * Browser-side session client. Every call goes to a same-origin Next Route
 * Handler under /api/*, which proxies the Go control plane. The browser never
 * touches the session cookie directly (it's HttpOnly) and never sees the
 * trusted-client-proof secret.
 */

export class SessionError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "SessionError";
  }
}

async function readError(response: Response): Promise<SessionError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) {
      message = payload.error.message;
    }
  } catch {
    // non-JSON body — keep the generic message
  }
  return new SessionError(message, code, response.status);
}

/** Fetch the current user + tenant/project memberships. Throws on 401. */
export async function fetchCurrentUser(): Promise<CurrentUser> {
  const response = await fetch("/api/me", {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as CurrentUser;
}

/** Fetch the CSRF token required for mutating, cookie-authenticated calls. */
export async function fetchCsrfToken(): Promise<string> {
  const response = await fetch("/api/auth/csrf-token", {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw await readError(response);
  }
  const payload = (await response.json()) as { csrf_token?: string };
  if (!payload.csrf_token) {
    throw new SessionError("未获取到安全令牌", "CSRF_UNAVAILABLE", response.status);
  }
  return payload.csrf_token;
}

/** Log out: fetch a CSRF token, then delete the session. */
export async function logout(): Promise<void> {
  const csrfToken = await fetchCsrfToken();
  const response = await fetch("/api/auth/session", {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
  // 204 is the success path; anything else is an error worth surfacing.
  if (!response.ok && response.status !== 204) {
    throw await readError(response);
  }
}
