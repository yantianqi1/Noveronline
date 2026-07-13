import { KeyRound } from "lucide-react";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { Bi } from "../../components/bilingual-text";
import { requestPasswordResetFromServer } from "../../lib/auth-recovery-server";
import { humanizeFailure } from "../../lib/user-facing-copy";

export default async function RecoveryPage({
  searchParams,
}: {
  searchParams?: Promise<{ requested?: string; error?: string }>;
}) {
  const query = searchParams ? await searchParams : {};

  async function requestAction(data: FormData) {
    "use server";
    const email = data.get("email");
    const result = await requestPasswordResetFromServer(
      typeof email === "string" ? email : "",
      await headers(),
    );
    redirect(
      result.ok
        ? "/recovery?requested=1"
        : `/recovery?error=${encodeURIComponent(result.code)}`,
    );
  }

  const errorMessage = query.error
    ? humanizeFailure("zh-CN", query.error)
    : null;

  return (
    <main className="app-main login-main">
      <section className="panel login-panel">
        <KeyRound aria-hidden="true" size={24} />
        <p className="eyebrow">
          <Bi zh="账户恢复" en="Account recovery" />
        </p>
        <h1>
          <Bi zh="重置密码" en="Reset password" />
        </h1>
        {query.requested ? (
          <p role="status">
            <Bi
              zh="如果账户符合条件，系统将尝试发送重置说明。"
              en="If the account is eligible, reset delivery will be attempted."
            />
          </p>
        ) : null}
        {errorMessage ? (
          <p className="error-box" data-code={query.error} role="alert">
            {errorMessage}
          </p>
        ) : null}
        <form action={requestAction}>
          <label htmlFor="recovery-email">
            <Bi zh="邮箱" en="Email" />
          </label>
          <input
            id="recovery-email"
            name="email"
            type="email"
            autoComplete="email"
            required
          />
          <button type="submit">
            <Bi zh="请求重置" en="Request reset" />
          </button>
        </form>
      </section>
    </main>
  );
}
