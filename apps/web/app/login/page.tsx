import { ArrowLeft, Feather } from "lucide-react";
import { cookies, headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { LoginForm } from "../../components/login-form";
import { loginWithPassword } from "../../lib/api";
import { createRecoveryClientProof } from "../../lib/auth-recovery-server";
import { devWorkspacePath, isDevLoginBypassEnabled } from "../../lib/dev-access";
import { workspacePathForProject } from "../../lib/workspace-route";

type LoginPageProps = {
  searchParams?: Promise<{
    login_status?: string;
    login_code?: string;
  }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  if (isDevLoginBypassEnabled()) {
    redirect(devWorkspacePath("overview"));
  }

  const query = (await searchParams) ?? {};

  async function loginAction(formData: FormData) {
    "use server";

    const email = stringFromFormData(formData, "email");
    const password = rawStringFromFormData(formData, "password");
    if (!email || !password) {
      redirect("/login?login_status=error&login_code=VALIDATION_FAILED");
    }

    const clientProof = createRecoveryClientProof(await headers());
    const result = await loginWithPassword({ email, password, clientProof });
    if (!result.ok) {
      redirect(`/login?login_status=error&login_code=${encodeURIComponent(result.code)}`);
    }

    const cookieStore = await cookies();
    cookieStore.set("mirofish_session", result.session_cookie.value, {
      httpOnly: result.session_cookie.http_only,
      maxAge: result.session_cookie.max_age,
      path: result.session_cookie.path,
      sameSite: result.session_cookie.same_site,
      secure: result.session_cookie.secure,
    });
    const project = result.active_projects[0];
    if (!project) {
      redirect("/invitations/accept");
    }
    redirect(workspacePathForProject(result.active_tenants, project, "overview"));
  }

  return (
    <main className="auth-shell login-main login-page">
      <div className="login-atmosphere" aria-hidden="true">
        <span className="login-atmosphere-mountains" />
        <span className="login-atmosphere-book" />
        <span className="login-atmosphere-constellation" />
        <span className="login-atmosphere-sun" />
      </div>
      <span className="login-seal" aria-hidden="true">
        执笔
      </span>

      <header className="auth-topbar">
        <Link className="auth-brand" href="/">
          <span className="auth-brand-mark" aria-hidden="true">
            MF
          </span>
          <span className="auth-brand-copy">
            <strong>MiroFish-Novel</strong>
            <small>长篇小说创作平台</small>
          </span>
        </Link>
        <Link className="auth-ghost-link" href="/" aria-label="返回首页">
          <ArrowLeft aria-hidden="true" size={17} strokeWidth={1.8} />
          <span className="auth-ghost-link-label">返回首页</span>
        </Link>
      </header>

      <div className="auth-stage">
        <section className="login-workspace" aria-labelledby="login-heading">
          <div className="login-form-panel">
            <div className="login-copy">
              <p className="login-kicker">
                <Feather aria-hidden="true" className="login-kicker-icon" size={16} strokeWidth={1.8} />
                创作工作台
              </p>
              <h1 id="login-heading">欢迎回来</h1>
              <p className="login-intro">登录后继续整理你的故事世界，衔接上一次创作进度。</p>

              {query.login_status === "error" ? (
                <div
                  className="login-error"
                  data-code={query.login_code || "PASSWORD_LOGIN_FAILED"}
                  role="alert"
                >
                  <strong>登录未成功</strong>
                  <p>请检查邮箱和密码，然后重新尝试。</p>
                </div>
              ) : null}

              <LoginForm action={loginAction} />

              <div className="login-join" aria-label="注册账号">
                <span aria-hidden="true" />
                <p>
                  还没有账号？ <Link href="/signup">免费注册</Link>
                </p>
                <span aria-hidden="true" />
              </div>
            </div>
          </div>

          <aside className="login-visual" aria-label="打开的书页与故事世界">
            <div className="login-visual-copy">
              <p>故事仍在继续</p>
              <h2>让每一章，都与整个世界保持连贯。</h2>
            </div>
          </aside>
        </section>
      </div>
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
