import { cookies } from "next/headers";

import { ProjectNav } from "../../../../../components/project-nav";
import { SessionAutoRefresh } from "../../../../../components/session-auto-refresh";
import {
  getCurrentUser,
  getCurrentUserSessions,
  getSessionCSRFToken,
  revokeAllCurrentUserSessions,
  revokeCurrentSession,
  rotateCurrentSession,
  type CurrentUserSummary,
} from "../../../../../lib/api";

export default async function ProjectLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ tenantSlug: string; projectId: string }>;
}>) {
  const { tenantSlug, projectId } = await params;
  const basePath = `/${tenantSlug}/projects/${projectId}`;
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("mirofish_session")?.value?.trim();
  const actorUserId = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim();
  async function revokeAllSessionsAction() {
    "use server";

    const actionCookieStore = await cookies();
    const actionSessionCookie = actionCookieStore.get("mirofish_session")?.value?.trim();
    if (!actionSessionCookie) {
      return;
    }
    const csrfResult = await getSessionCSRFToken({ sessionCookie: actionSessionCookie });
    if (!csrfResult.ok) {
      return;
    }
    const result = await revokeAllCurrentUserSessions({ sessionCookie: actionSessionCookie, csrfToken: csrfResult.csrf_token });
    if (result.ok) {
      actionCookieStore.delete("mirofish_session");
    }
  }

  async function rotateSessionAction() {
    "use server";

    const actionCookieStore = await cookies();
    const actionSessionCookie = actionCookieStore.get("mirofish_session")?.value?.trim();
    if (!actionSessionCookie) {
      return;
    }
    const csrfResult = await getSessionCSRFToken({ sessionCookie: actionSessionCookie });
    if (!csrfResult.ok) {
      return;
    }
    const rotationResult = await rotateCurrentSession({
      sessionCookie: actionSessionCookie,
      csrfToken: csrfResult.csrf_token,
    });
    if (!rotationResult.ok) {
      return;
    }
    actionCookieStore.set("mirofish_session", rotationResult.session_cookie.value, {
      httpOnly: rotationResult.session_cookie.http_only,
      maxAge: rotationResult.session_cookie.max_age,
      path: rotationResult.session_cookie.path,
      sameSite: rotationResult.session_cookie.same_site,
      secure: rotationResult.session_cookie.secure,
    });
  }

  async function logoutAction() {
    "use server";

    const actionCookieStore = await cookies();
    const actionSessionCookie = actionCookieStore.get("mirofish_session")?.value?.trim();
    if (!actionSessionCookie) {
      return;
    }
    const csrfResult = await getSessionCSRFToken({ sessionCookie: actionSessionCookie });
    if (!csrfResult.ok) {
      return;
    }
    const result = await revokeCurrentSession({ sessionCookie: actionSessionCookie, csrfToken: csrfResult.csrf_token });
    if (result.ok) {
      actionCookieStore.delete("mirofish_session");
    }
  }

  const currentUserSessions = sessionCookie ? await getCurrentUserSessions({ sessionCookie }) : undefined;
  const currentUser: CurrentUserSummary = sessionCookie || actorUserId
    ? await getCurrentUser({
        actorUserId: sessionCookie ? undefined : actorUserId,
        sessionCookie,
      })
    : {
        ok: false,
        code: "CURRENT_USER_CONTEXT_UNCONFIGURED",
        message: "current user context is not configured",
        request_id: "",
      };

  return (
    <div className="app-frame">
      <SessionAutoRefresh enabled={Boolean(sessionCookie)} />
      <aside className="app-sidebar" aria-label="Project navigation">
        <ProjectNav
          basePath={basePath}
          currentUser={currentUser}
          currentUserSessions={currentUserSessions}
          logoutAction={logoutAction}
          projectId={projectId}
          revokeAllSessionsAction={revokeAllSessionsAction}
          rotateSessionAction={rotateSessionAction}
          tenantSlug={tenantSlug}
        />
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
