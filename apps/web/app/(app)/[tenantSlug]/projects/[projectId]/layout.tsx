import { ProjectNav } from "../../../../../components/project-nav";
import { SessionAutoRefresh } from "../../../../../components/session-auto-refresh";
import {
  getCurrentUser,
  getCurrentUserSessions,
  type CurrentUserSummary,
} from "../../../../../lib/api";
import { currentRequestSessionCookie } from "../../../../../lib/request-session";
import {
  logoutAction,
  revokeAllSessionsAction,
  revokeTenantSessionsAction,
  rotateSessionAction,
} from "./session-actions";

export default async function ProjectLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ tenantSlug: string; projectId: string }>;
}>) {
  const { tenantSlug, projectId } = await params;
  const basePath = `/${tenantSlug}/projects/${projectId}`;
  const sessionCookie = currentRequestSessionCookie({ required: true });
  const actorUserId = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim();

  const currentUserSessions = sessionCookie ? await getCurrentUserSessions({ sessionCookie }) : undefined;
  const currentSessionExpiresAt = currentUserSessions?.ok ? currentUserSessions.sessions.find((session) => session.current)?.expires_at : undefined;
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
      <SessionAutoRefresh currentSessionExpiresAt={currentSessionExpiresAt} enabled={Boolean(sessionCookie)} />
      <aside className="app-sidebar" aria-label="Project navigation">
        <ProjectNav
          basePath={basePath}
          currentUser={currentUser}
          currentUserSessions={currentUserSessions}
          logoutAction={logoutAction}
          projectId={projectId}
          revokeTenantSessionsAction={revokeTenantSessionsAction.bind(null, tenantSlug)}
          revokeAllSessionsAction={revokeAllSessionsAction}
          rotateSessionAction={rotateSessionAction}
          tenantSlug={tenantSlug}
        />
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
