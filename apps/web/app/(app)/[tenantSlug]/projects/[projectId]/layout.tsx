import { cookies } from "next/headers";

import { ProjectNav } from "../../../../../components/project-nav";
import { getCurrentUser, type CurrentUserSummary } from "../../../../../lib/api";

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
          projectId={projectId}
          tenantSlug={tenantSlug}
        />
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
