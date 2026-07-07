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
  const actorUserId = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim();
  const currentUser: CurrentUserSummary = actorUserId
    ? await getCurrentUser({ actorUserId })
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
