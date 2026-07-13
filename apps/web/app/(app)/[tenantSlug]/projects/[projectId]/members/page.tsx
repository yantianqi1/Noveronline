import { redirect } from "next/navigation";
import { MembersWorkspace } from "../../../../../../components/members-workspace";
import {
  changeProjectMember,
  changeTenantMember,
  createProjectInvitation,
  listProjectInvitations,
  listProjectMembers,
  listTenantMembers,
  removeProjectMember,
  removeTenantMember,
  resendInvitation,
  revokeInvitation,
} from "../../../../../../lib/collaboration-api";
import { webApiContext } from "../../../../../../lib/server-auth";

export const dynamic = "force-dynamic";

export default async function MembersPage({params, searchParams}:{
  params: Promise<{tenantSlug:string;projectId:string}>;
  searchParams?: Promise<{members_error?:string}>;
}) {
  const {tenantSlug, projectId} = await params;
  const query = searchParams ? await searchParams : {};
  const context = await webApiContext({tenantId: tenantSlug});
  const [projectResult, invitationResult, tenantResult] = await Promise.all([
    listProjectMembers({...context, projectId}),
    listProjectInvitations({...context, projectId}),
    listTenantMembers(context),
  ]);
  const basePath = `/${tenantSlug}/projects/${projectId}/members`;

  async function inviteAction(data:FormData) {
    "use server";
    const actionContext = await webApiContext({tenantId: tenantSlug});
    const result = await createProjectInvitation({...actionContext, projectId, email:text(data,"email"), projectRole:text(data,"role")});
    redirectMembers(basePath, result.ok ? undefined : result.code);
  }
  async function memberAction(data:FormData) {
    "use server";
    const actionContext = await webApiContext({tenantId: tenantSlug});
    const userId = text(data,"userId");
    const operation = text(data,"operation");
    const result = operation === "remove"
      ? await removeProjectMember({...actionContext, projectId, userId})
      : await changeProjectMember({...actionContext, projectId, userId, ...(operation === "role" ? {role:text(data,"role")} : {status:operation === "suspend" ? "suspended" : "active"})});
    redirectMembers(basePath, result.ok ? undefined : result.code);
  }
  async function tenantMemberAction(data:FormData) {
    "use server";
    const actionContext = await webApiContext({tenantId: tenantSlug});
    const userId = text(data,"userId");
    const operation = text(data,"operation");
    const result = operation === "remove"
      ? await removeTenantMember({...actionContext, userId})
      : await changeTenantMember({...actionContext, userId, ...(operation === "role" ? {role:text(data,"role")} : {status:operation === "suspend" ? "suspended" : "active"})});
    redirectMembers(basePath, result.ok ? undefined : result.code);
  }
  async function invitationAction(data:FormData) {
    "use server";
    const actionContext = await webApiContext({tenantId: tenantSlug});
    const invitationId = text(data,"invitationId");
    const result = text(data,"operation") === "resend"
      ? await resendInvitation({...actionContext, invitationId})
      : await revokeInvitation({...actionContext, invitationId});
    redirectMembers(basePath, result.ok ? undefined : result.code);
  }
  const tenantError = tenantResult.ok || tenantResult.code === "COLLABORATION_ACCESS_DENIED" ? undefined : tenantResult.code;
  const error = query.members_error || (!projectResult.ok ? projectResult.code : !invitationResult.ok ? invitationResult.code : tenantError);
  return <MembersWorkspace
    members={projectResult.ok ? projectResult.members : []}
    tenantMembers={tenantResult.ok ? tenantResult.members : undefined}
    invitations={invitationResult.ok ? invitationResult.invitations : []}
    error={error}
    inviteAction={inviteAction}
    memberAction={memberAction}
    tenantMemberAction={tenantMemberAction}
    invitationAction={invitationAction}
  />;
}

function text(data:FormData, key:string) {
  const value = data.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function redirectMembers(basePath:string, code?:string):never {
  const publicCode = code === "LAST_ACTIVE_OWNER_REQUIRED" ? `LAST_OWNER:${code}` : code;
  redirect(publicCode ? `${basePath}?members_error=${encodeURIComponent(publicCode)}` : basePath);
}
