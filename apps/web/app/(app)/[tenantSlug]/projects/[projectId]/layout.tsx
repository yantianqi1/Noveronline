import { cookies } from "next/headers";

import { ProjectNav } from "../../../../../components/project-nav";
import { getCurrentUser, revokeCurrentSession, type CurrentUserSummary } from "../../../../../lib/api";

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
  async function logoutAction() {
    "use server";

    const actionCookieStore = await cookies();
    const actionSessionCookie = actionCookieStore.get("mirofish_session")?.value?.trim();
    if (!actionSessionCookie) {
      return;
    }
    const result = await revokeCurrentSession({ sessionCookie: actionSessionCookie });
    if (result.ok) {
      actionCookieStore.delete("mirofish_session");
    }
  }

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
      <aside className="app-sidebar" aria-label="Project navigation">
        <ProjectNav
          basePath={basePath}
          currentUser={currentUser}
          logoutAction={logoutAction}
          projectId={projectId}
          tenantSlug={tenantSlug}
        />
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
