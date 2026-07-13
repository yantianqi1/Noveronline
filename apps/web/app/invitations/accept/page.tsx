import { BadgeCheck } from "lucide-react";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Bi } from "../../../components/bilingual-text";
import { acceptInvitation } from "../../../lib/collaboration-api";
import { getSessionCSRFToken } from "../../../lib/api";
import { createRecoveryClientProof } from "../../../lib/auth-recovery-server";
import { currentRequestSessionCookie } from "../../../lib/request-session";

export const dynamic="force-dynamic";
export default async function AcceptInvitationPage({searchParams}:{searchParams:Promise<{token?:string;status?:string;code?:string}>}){const query=await searchParams;const invitationToken=query.token?.trim()??"";async function acceptAction(){"use server";const sessionCookie=currentRequestSessionCookie({required:true});const csrf=await getSessionCSRFToken({sessionCookie});if(!csrf.ok)redirect(`/invitations/accept?status=error&code=${encodeURIComponent(csrf.code)}`);const clientProof=createRecoveryClientProof(await headers());if(!clientProof)redirect("/invitations/accept?status=error&code=RATE_LIMIT_BACKEND_UNAVAILABLE");const result=await acceptInvitation({token:invitationToken,sessionCookie,csrfToken:csrf.csrf_token,clientProof});redirect(result.ok?"/invitations/accept?status=accepted":`/invitations/accept?status=error&code=${encodeURIComponent(result.code)}`)}return <main className="app-main login-main"><section className="panel login-panel"><BadgeCheck aria-hidden="true" size={24}/><p className="eyebrow"><Bi zh="协作邀请" en="Collaboration invitation"/></p><h1><Bi zh="加入项目" en="Join project"/></h1>{query.status==="accepted"?<p role="status"><Bi zh="邀请已接受。" en="Invitation accepted."/></p>:query.status==="error"?<p className="error-box" role="alert">{query.code}</p>:<form action={acceptAction}><button type="submit" disabled={!invitationToken}><Bi zh="接受邀请" en="Accept invitation"/></button></form>}</section></main>}
