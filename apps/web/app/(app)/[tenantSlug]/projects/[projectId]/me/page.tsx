import { MeHub } from "../../../../../../components/me-hub";
import { getCurrentUser, type CurrentUserSummary } from "../../../../../../lib/api";
import { devActorUserId, isDevLoginBypassEnabled } from "../../../../../../lib/dev-access";
import { currentRequestSessionCookie } from "../../../../../../lib/request-session";
import { workspaceBasePathForProject, workspacePathForProject } from "../../../../../../lib/workspace-route";
import { logoutAction } from "../session-actions";

export const dynamic = "force-dynamic";

export default async function MePage({
  params,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
}) {
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
    ? currentUser.active_projects.find(
        (project) => project.tenant_id === tenantSlug && project.project_id === projectId,
      )
    : undefined;
  const basePath = currentUser.ok && currentProject
    ? workspaceBasePathForProject(currentUser.active_tenants, currentProject)
    : `/${tenantSlug}/projects/${projectId}`;
  const tenants = currentUser.ok ? currentUser.active_tenants : [];
  const llmHref = currentProject
    ? workspacePathForProject(tenants, currentProject, "/llm-facility")
    : `${basePath}/llm`;
  const securityHref = currentProject
    ? workspacePathForProject(tenants, currentProject, "/security")
    : `${basePath}/security`;

  return (
    <MeHub
      changePasswordHref={securityHref}
      currentUser={currentUser}
      llmHref={llmHref}
      logoutAction={logoutAction}
      securityHref={securityHref}
    />
  );
}
