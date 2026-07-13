import { Bi } from "../../../../../components/bilingual-text";
import { ProjectNav } from "../../../../../components/project-nav";
import { SessionAutoRefresh } from "../../../../../components/session-auto-refresh";
import { WorkspaceContextBar } from "../../../../../components/workspace-context-bar";
import { WorkspaceRouteTransition } from "../../../../../components/workspace-route-transition";
import {
  getCurrentUser,
  type CurrentUserSummary,
} from "../../../../../lib/api";
import { devActorUserId, isDevLoginBypassEnabled } from "../../../../../lib/dev-access";
import { currentRequestSessionCookie } from "../../../../../lib/request-session";
import { workspaceBasePathForProject } from "../../../../../lib/workspace-route";
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
  const sessionCookie = currentRequestSessionCookie({
    required: !isDevLoginBypassEnabled(),
  });
  const actorUserId = devActorUserId();

  const loadedCurrentUser = sessionCookie || actorUserId
    ? await getCurrentUser({
        actorUserId: sessionCookie ? undefined : actorUserId,
        sessionCookie,
      })
    : {
        ok: false as const,
        code: "CURRENT_USER_CONTEXT_UNCONFIGURED",
        message: "current user context is not configured",
        request_id: "",
      };
  const currentUser: CurrentUserSummary = loadedCurrentUser;
  const currentProject = currentUser.ok
    ? currentUser.active_projects.find((project) => project.tenant_id === tenantSlug && project.project_id === projectId)
    : undefined;
  const basePath = currentUser.ok && currentProject
    ? workspaceBasePathForProject(currentUser.active_tenants, currentProject)
    : `/${tenantSlug}/projects/${projectId}`;

  return (
    <div className="app-frame app-frame-unified">
      <a className="skip-link" href="#workspace-main">
        <Bi zh="跳到工作区" en="Skip to workspace" />
      </a>
      <SessionAutoRefresh enabled={Boolean(sessionCookie)} />
      <aside className="app-sidebar" aria-label="项目导航 / Project navigation">
        <ProjectNav
          basePath={basePath}
          currentUser={currentUser}
          changePasswordHref={`${basePath}/security`}
          logoutAction={logoutAction}
          projectId={projectId}
          revokeTenantSessionsAction={revokeTenantSessionsAction.bind(null, tenantSlug)}
          revokeAllSessionsAction={revokeAllSessionsAction}
          rotateSessionAction={rotateSessionAction}
          tenantSlug={tenantSlug}
        />
      </aside>
      <div className="app-main-shell">
        <WorkspaceContextBar
          projectName={currentProject?.name || <Bi zh="当前项目" en="Current project" />}
        />
        <main className="app-main" id="workspace-main" tabIndex={-1}>
          <WorkspaceRouteTransition>{children}</WorkspaceRouteTransition>
        </main>
      </div>
    </div>
  );
}
