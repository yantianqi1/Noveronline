"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
	changePassword,
	getSessionCSRFToken,
  revokeAllCurrentUserSessions,
  revokeCurrentSession,
  revokeTenantSessions,
  rotateCurrentSession,
} from "../../../../../lib/api";

export async function changePasswordAction(securityPath: string, formData: FormData) {
	"use server";

	const currentPassword = passwordFromFormData(formData, "currentPassword");
	const newPassword = passwordFromFormData(formData, "newPassword");
	const confirmPassword = passwordFromFormData(formData, "confirmPassword");
	if (!currentPassword || !newPassword || newPassword !== confirmPassword) {
		redirect(`${securityPath}?password_error=VALIDATION_FAILED`);
	}
	const { actionCookieStore, actionSessionCookie } = await readActionSessionCookie();
	if (!actionSessionCookie) {
		redirect("/login?error=SESSION_REQUIRED");
	}
	const csrfResult = await requireActionCSRFToken(actionSessionCookie);
	const result = await changePassword({
		currentPassword,
		newPassword,
		sessionCookie: actionSessionCookie,
		csrfToken: csrfResult.csrf_token,
	});
	if (!result.ok) {
		const errorCode = result.code === "VALIDATION_FAILED" || result.code === "UNAUTHENTICATED"
			? result.code
			: "PASSWORD_CHANGE_FAILED";
		redirect(`${securityPath}?password_error=${errorCode}`);
	}
	actionCookieStore.delete("mirofish_session");
	redirect("/login?password_changed=1");
}

export async function logoutAction() {
  "use server";

  const { actionCookieStore, actionSessionCookie } = await readActionSessionCookie();
  if (!actionSessionCookie) {
    redirect("/login");
  }
  const csrfResult = await requireActionCSRFToken(actionSessionCookie);
  const result = await revokeCurrentSession({ sessionCookie: actionSessionCookie, csrfToken: csrfResult.csrf_token });
  if (!result.ok) {
    throw new Error("SESSION_REVOKE_FAILED");
  }
  actionCookieStore.delete("mirofish_session");
  redirect("/login");
}

export async function rotateSessionAction() {
  "use server";

  const { actionCookieStore, actionSessionCookie } = await readActionSessionCookie();
  if (!actionSessionCookie) {
    return;
  }
  const csrfResult = await requireActionCSRFToken(actionSessionCookie);
  const rotationResult = await rotateCurrentSession({
    sessionCookie: actionSessionCookie,
    csrfToken: csrfResult.csrf_token,
  });
  if (!rotationResult.ok) {
    throw new Error("SESSION_ROTATION_FAILED");
  }
  actionCookieStore.set("mirofish_session", rotationResult.session_cookie.value, {
    httpOnly: rotationResult.session_cookie.http_only,
    maxAge: rotationResult.session_cookie.max_age,
    path: rotationResult.session_cookie.path,
    sameSite: rotationResult.session_cookie.same_site,
    secure: rotationResult.session_cookie.secure,
  });
}

export async function revokeAllSessionsAction() {
  "use server";

  const { actionCookieStore, actionSessionCookie } = await readActionSessionCookie();
  if (!actionSessionCookie) {
    return;
  }
  const csrfResult = await requireActionCSRFToken(actionSessionCookie);
  const result = await revokeAllCurrentUserSessions({ sessionCookie: actionSessionCookie, csrfToken: csrfResult.csrf_token });
  if (!result.ok) {
    throw new Error("SESSION_REVOKE_FAILED");
  }
  actionCookieStore.delete("mirofish_session");
}

export async function revokeTenantSessionsAction(tenantId: string) {
  "use server";

  const { actionCookieStore, actionSessionCookie } = await readActionSessionCookie();
  if (!actionSessionCookie) {
    return;
  }
  const csrfResult = await requireActionCSRFToken(actionSessionCookie);
  const result = await revokeTenantSessions({ tenantId, sessionCookie: actionSessionCookie, csrfToken: csrfResult.csrf_token });
  if (!result.ok) {
    throw new Error("TENANT_SESSION_REVOKE_FAILED");
  }
  actionCookieStore.delete("mirofish_session");
}

async function readActionSessionCookie() {
  const actionCookieStore = await cookies();
  const actionSessionCookie = actionCookieStore.get("mirofish_session")?.value?.trim();
  return { actionCookieStore, actionSessionCookie };
}

async function requireActionCSRFToken(actionSessionCookie: string) {
  const csrfResult = await getSessionCSRFToken({ sessionCookie: actionSessionCookie });
  if (!csrfResult.ok) {
    throw new Error("SESSION_CSRF_TOKEN_UNAVAILABLE");
  }
	return csrfResult;
}

function passwordFromFormData(formData: FormData, field: string) {
	const value = formData.get(field);
	return typeof value === "string" ? value : "";
}
