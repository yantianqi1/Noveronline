import { KeyRound } from "lucide-react";

import { Bi } from "../../../../../../components/bilingual-text";
import { PublicErrorNotice } from "../../../../../../components/public-error-notice";
import { changePasswordAction } from "../session-actions";

export const dynamic = "force-dynamic";

export default async function SecurityPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{ password_error?: string }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const securityPath = `/${tenantSlug}/projects/${projectId}/security`;
  const hasPasswordError = isPublicPasswordError(query.password_error);

  return (
    <div>
      <header>
        <p className="eyebrow"><Bi zh="账户" en="Account" /></p>
        <h1>
          <span className="page-title-icon" aria-hidden="true"><KeyRound size={22} strokeWidth={1.8} /></span>
          <Bi zh="账户安全" en="Account security" />
        </h1>
      </header>

      <div className="workbench-grid">
        <main>
          <section className="panel" aria-labelledby="change-password-heading">
            <p className="eyebrow"><Bi zh="凭据" en="Credentials" /></p>
            <h2 id="change-password-heading"><Bi zh="修改密码" en="Change password" /></h2>
            {hasPasswordError ? (
              <PublicErrorNotice
                message={<Bi zh="密码未修改。请确认当前密码与新密码要求后重试。" en="The password was not changed. Confirm the current password and new password requirements, then try again." />}
                recovery={<Bi zh="新密码至少 12 个字符。" en="Use a new password of at least 12 characters." />}
                title={<Bi zh="无法更新密码" en="Unable to update password" />}
              />
            ) : null}
            <form action={changePasswordAction.bind(null, securityPath)}>
              <label htmlFor="current-password"><Bi zh="当前密码" en="Current password" /></label>
              <input
                autoComplete="current-password"
                id="current-password"
                name="currentPassword"
                required
                type="password"
              />
              <label htmlFor="new-password"><Bi zh="新密码" en="New password" /></label>
              <input
                autoComplete="new-password"
                id="new-password"
                maxLength={72}
                minLength={12}
                name="newPassword"
                required
                type="password"
              />
              <label htmlFor="confirm-password"><Bi zh="确认新密码" en="Confirm new password" /></label>
              <input
                autoComplete="new-password"
                id="confirm-password"
                maxLength={72}
                minLength={12}
                name="confirmPassword"
                required
                type="password"
              />
              <button type="submit">
                <KeyRound aria-hidden="true" size={16} />
                <Bi zh="更新密码" en="Update password" />
              </button>
            </form>
          </section>
        </main>
      </div>
    </div>
  );
}

function isPublicPasswordError(value: string | undefined) {
  const normalized = value?.trim() ?? "";
  return normalized === "VALIDATION_FAILED"
    || normalized === "UNAUTHENTICATED"
    || normalized === "PASSWORD_CHANGE_FAILED";
}
