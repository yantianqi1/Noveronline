import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { loginWithPassword } from "../../lib/api";

type LoginPageProps = {
  searchParams?: Promise<{
    login_status?: string;
    login_code?: string;
  }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const query = (await searchParams) ?? {};

  async function loginAction(formData: FormData) {
    "use server";

    const email = stringFromFormData(formData, "email");
    const password = rawStringFromFormData(formData, "password");
    if (!email || !password) {
      redirect("/login?login_status=error&login_code=VALIDATION_FAILED");
    }

    const result = await loginWithPassword({ email, password });
    if (!result.ok) {
      redirect(`/login?login_status=error&login_code=${encodeURIComponent(result.code)}`);
    }

    const project = result.active_projects[0];
    if (!project) {
      redirect("/login?login_status=error&login_code=ACTIVE_PROJECT_MEMBERSHIP_MISSING");
    }

    const cookieStore = await cookies();
    cookieStore.set("mirofish_session", result.session_cookie.value, {
      httpOnly: result.session_cookie.http_only,
      maxAge: result.session_cookie.max_age,
      path: result.session_cookie.path,
      sameSite: result.session_cookie.same_site,
      secure: result.session_cookie.secure,
    });
    redirect(`/${project.tenant_id}/projects/${project.project_id}/overview`);
  }

  return (
    <main className="app-main login-main">
      <section className="panel login-panel" aria-labelledby="login-heading">
        <p className="eyebrow">MiroFish SaaS</p>
        <h1 id="login-heading">Sign in</h1>
        {query.login_status === "error" ? (
          <div className="error-box" role="status">
            <strong>Login unavailable</strong>
            <p>{query.login_code || "PASSWORD_LOGIN_FAILED"}</p>
          </div>
        ) : null}
        <form action={loginAction} className="binding-form">
          <label htmlFor="login-email">Email</label>
          <input id="login-email" name="email" type="email" autoComplete="email" required />

          <label htmlFor="login-password">Password</label>
          <input id="login-password" name="password" type="password" autoComplete="current-password" required />

          <button type="submit">Sign in</button>
        </form>
      </section>
    </main>
  );
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function rawStringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value : "";
}
