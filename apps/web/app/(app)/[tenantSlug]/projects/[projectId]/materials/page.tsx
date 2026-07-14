import { MaterialsHub } from "../../../../../../components/materials-hub";
import { getCurrentUser } from "../../../../../../lib/api";
import { devActorUserId, isDevLoginBypassEnabled } from "../../../../../../lib/dev-access";
import { currentRequestSessionCookie } from "../../../../../../lib/request-session";
import { workspaceBasePathForProject } from "../../../../../../lib/workspace-route";

export const dynamic = "force-dynamic";

export default async function MaterialsPage({
  params,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
}) {
  const { tenantSlug, projectId } = await params;
  const sessionCookie = currentRequestSessionCookie({
    required: !isDevLoginBypassEnabled(),
  });
  const actorUserId = devActorUserId();
  const currentUser = sessionCookie || actorUserId
    ? await getCurrentUser({
        actorUserId: sessionCookie ? undefined : actorUserId,
        sessionCookie,
      })
    : { ok: false as const };
  const currentProject = currentUser.ok
    ? currentUser.active_projects.find(
        (project) => project.tenant_id === tenantSlug && project.project_id === projectId,
      )
    : undefined;
  const basePath = currentUser.ok && currentProject
    ? workspaceBasePathForProject(currentUser.active_tenants, currentProject)
    : `/${tenantSlug}/projects/${projectId}`;
  const tenantName = currentUser.ok
    ? currentUser.active_tenants.find((tenant) => tenant.tenant_id === tenantSlug)?.name
    : undefined;

  return (
    <MaterialsHub
      basePath={basePath}
      projectId={projectId}
      projectName={currentProject?.name}
      tenantName={tenantName}
      tenantSlug={tenantSlug}
    />
  );
}
