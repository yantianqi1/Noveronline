import { MailPlus, ShieldCheck, UserRoundCog, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import type { CollaborationInvitation, CollaborationMember } from "../lib/collaboration-api";
import { Bi } from "./bilingual-text";
import { PublicErrorNotice } from "./public-error-notice";

type MemberAction = (data: FormData) => Promise<void>;

type MembersWorkspaceProps = {
  members: CollaborationMember[];
  tenantMembers?: CollaborationMember[];
  invitations: CollaborationInvitation[];
  error?: string;
  inviteAction: MemberAction;
  memberAction: MemberAction;
  tenantMemberAction: MemberAction;
  invitationAction: MemberAction;
};

export function MembersWorkspace({
  members,
  tenantMembers,
  invitations,
  error,
  inviteAction,
  memberAction,
  tenantMemberAction,
  invitationAction,
}: MembersWorkspaceProps) {
  return <div>
    <header>
      <p className="eyebrow"><Bi zh="协作" en="Collaboration" /></p>
      <h1><span className="page-title-icon" aria-hidden="true"><UsersRound size={22}/></span><Bi zh="成员管理" en="Member management" /></h1>
    </header>
    {error ? (
      <PublicErrorNotice
        message={<Bi zh="成员操作未完成。请检查权限后重试。" en="The member action did not complete. Check permissions and try again." />}
        recovery={<Bi zh="刷新页面后重试，或联系工作区管理员。" en="Refresh and retry, or contact a workspace admin." />}
        title={<Bi zh="协作操作失败" en="Collaboration action failed" />}
      />
    ) : null}
    <div className="workbench-grid">
      <main>
        {tenantMembers ? <MemberTable
          headingId="tenant-member-list-heading"
          heading={<Bi zh="工作区成员" en="Workspace members" />}
          members={tenantMembers}
          action={tenantMemberAction}
          scope="tenant"
        /> : null}
        <MemberTable
          headingId="project-member-list-heading"
          heading={<Bi zh="项目成员" en="Project members" />}
          members={members}
          action={memberAction}
          scope="project"
        />
        <InvitationTable invitations={invitations} action={invitationAction} />
      </main>
      <aside><InvitePanel action={inviteAction} /></aside>
    </div>
  </div>;
}

function MemberTable({headingId, heading, members, action, scope}:{
  headingId: string;
  heading: ReactNode;
  members: CollaborationMember[];
  action: MemberAction;
  scope: "tenant" | "project";
}) {
  const roles = scope === "tenant"
    ? [["owner", "Owner"], ["admin", "Admin"], ["editor", "Editor"], ["writer", "Writer"], ["viewer", "Viewer"], ["billing", "Billing"]]
    : [["project_owner", "Project owner"], ["editor", "Editor"], ["writer", "Writer"], ["analyst", "Analyst"], ["viewer", "Viewer"]];
  return <section className="panel" aria-labelledby={headingId} data-member-scope={scope}>
    <h2 id={headingId}>{heading}</h2>
    <div className="table-wrap"><table>
      <thead><tr><th><Bi zh="成员" en="Member" /></th><th><Bi zh="角色" en="Role" /></th><th><Bi zh="状态" en="Status" /></th><th><Bi zh="操作" en="Actions" /></th></tr></thead>
      <tbody>{members.map(member => <tr key={member.user_id}>
        <td><strong>{member.display_name}</strong><br/><small>{member.email}</small></td>
        <td><form action={action}>
          <input type="hidden" name="userId" value={member.user_id}/>
          <select name="role" defaultValue={member.role} aria-label={`${scope} role for ${member.display_name}`}>
            {roles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <button type="submit" name="operation" value="role" title="Update role"><UserRoundCog aria-hidden="true" size={16}/></button>
        </form></td>
        <td>{member.status}</td>
        <td><form action={action}>
          <input type="hidden" name="userId" value={member.user_id}/>
          <button type="submit" name="operation" value={member.status === "suspended" ? "reactivate" : "suspend"}>{member.status === "suspended" ? <Bi zh="恢复" en="Reactivate"/> : <Bi zh="暂停" en="Suspend"/>}</button>
          <button type="submit" name="operation" value="remove"><Bi zh="移除" en="Remove"/></button>
        </form></td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

function InvitationTable({invitations, action}:{invitations:CollaborationInvitation[];action:MemberAction}) {
  return <section className="panel" aria-labelledby="invitation-list-heading">
    <h2 id="invitation-list-heading"><Bi zh="邀请状态" en="Invitation status"/></h2>
    <div className="table-wrap"><table>
      <thead><tr><th><Bi zh="邮箱" en="Email"/></th><th><Bi zh="角色" en="Role"/></th><th><Bi zh="状态" en="Status"/></th><th><Bi zh="投递" en="Delivery"/></th><th><Bi zh="操作" en="Actions"/></th></tr></thead>
      <tbody>{invitations.map(invitation => <tr key={invitation.invitation_id}>
        <td>{invitation.email}</td><td>{invitation.project_role}</td><td>{invitation.status}</td><td>{invitation.delivery_status}</td>
        <td>{invitation.status === "pending" ? <form action={action}>
          <input type="hidden" name="invitationId" value={invitation.invitation_id}/>
          <button name="operation" value="resend" type="submit"><Bi zh="重发" en="Resend"/></button>
          <button name="operation" value="revoke" type="submit"><Bi zh="撤销" en="Revoke"/></button>
        </form> : null}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

function InvitePanel({action}:{action:MemberAction}) {
  return <section className="panel" aria-labelledby="invite-heading">
    <MailPlus aria-hidden="true" size={20}/><h2 id="invite-heading"><Bi zh="邀请成员" en="Invite member" /></h2>
    <form action={action}>
      <label htmlFor="invite-email"><Bi zh="邮箱" en="Email" /></label><input id="invite-email" name="email" type="email" autoComplete="email" required/>
      <label htmlFor="invite-role"><Bi zh="项目角色" en="Project role" /></label><select id="invite-role" name="role" defaultValue="writer"><option value="editor">Editor</option><option value="writer">Writer</option><option value="analyst">Analyst</option><option value="viewer">Viewer</option></select>
      <button type="submit"><ShieldCheck aria-hidden="true" size={16}/><Bi zh="发送邀请" en="Send invitation" /></button>
    </form>
  </section>;
}
