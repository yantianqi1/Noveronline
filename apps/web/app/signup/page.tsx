import { ArrowLeft } from "lucide-react";
import { cookies, headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { SignupForm, type SignupFieldName, type SignupFormState } from "../../components/signup-form";
import { createRecoveryClientProof } from "../../lib/auth-recovery-server";
import { registerAccount } from "../../lib/registration-api";
import { workspacePathForProject } from "../../lib/workspace-route";

export default function SignupPage() {
  async function signupAction(_state: SignupFormState, formData: FormData): Promise<SignupFormState> {
    "use server";

    const displayName = stringFromFormData(formData, "display_name");
    const email = stringFromFormData(formData, "email").toLowerCase();
    const password = rawStringFromFormData(formData, "password");
    const confirmation = rawStringFromFormData(formData, "confirmation");
    const projectTitle = stringFromFormData(formData, "project_title");
    const fieldErrors = validateSignup({ displayName, email, password, confirmation, projectTitle });
    if (Object.keys(fieldErrors).length > 0) {
      return {
        ok: false,
        code: "VALIDATION_FAILED",
        message: "请修正标出的内容后重新提交。",
        fieldErrors,
      };
    }

    const clientProof = createRecoveryClientProof(await headers());
    const result = await registerAccount({ displayName, email, password, projectTitle, clientProof });
    if (!result.ok) {
      return registrationFailure(result.code);
    }

    const project = result.active_projects[0];
    const cookieStore = await cookies();
    cookieStore.set("mirofish_session", result.session_cookie.value, {
      httpOnly: result.session_cookie.http_only,
      maxAge: result.session_cookie.max_age,
      path: result.session_cookie.path,
      sameSite: result.session_cookie.same_site,
      secure: result.session_cookie.secure,
    });
    redirect(workspacePathForProject(result.active_tenants, project, "overview"));
  }

  return (
    <main className="auth-shell login-main login-page signup-page">
      <header className="auth-topbar">
        <Link className="auth-brand" href="/">
          <span className="auth-brand-mark" aria-hidden="true">MF</span>
          <span className="auth-brand-copy">
            <strong>MiroFish-Novel</strong>
            <small>长篇小说创作平台</small>
          </span>
        </Link>
        <Link className="auth-ghost-link" href="/login">
          <ArrowLeft aria-hidden="true" size={17} strokeWidth={1.8} />
          返回登录
        </Link>
      </header>

      <div className="auth-stage">
        <section className="login-workspace signup-workspace" aria-labelledby="signup-heading">
          <div className="login-form-panel">
            <div className="login-copy signup-copy">
              <p className="login-kicker">开始新的故事</p>
              <h1 id="signup-heading">创建你的账号</h1>
              <p className="login-intro">账号与第一本小说将保存在你的个人工作区。</p>

              <SignupForm action={signupAction} />

              <div className="login-join" aria-label="返回登录">
                <span aria-hidden="true" />
                <p>已有账号？ <Link href="/login">直接登录</Link></p>
                <span aria-hidden="true" />
              </div>
            </div>
          </div>

          <aside className="login-visual" aria-label="打开的书页与故事世界">
            <div className="login-visual-copy">
              <p>写下第一章</p>
              <h2>你的故事、设定和手稿，只属于你的工作区。</h2>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

function validateSignup(input: {
  displayName: string;
  email: string;
  password: string;
  confirmation: string;
  projectTitle: string;
}) {
  const errors: Partial<Record<SignupFieldName, string>> = {};
  const displayNameLength = Array.from(input.displayName).length;
  const projectTitleLength = Array.from(input.projectTitle).length;
  if (displayNameLength < 1 || displayNameLength > 120) errors.display_name = "称呼必须为 1 至 120 个字符。";
  if (!/^\S+@\S+\.\S+$/.test(input.email) || new TextEncoder().encode(input.email).length > 254) {
    errors.email = "请输入有效的邮箱地址。";
  }
  const passwordBytes = new TextEncoder().encode(input.password).length;
  if (passwordBytes < 12 || passwordBytes > 72) errors.password = "密码长度必须为 12 至 72 个字节。";
  if (!input.confirmation || input.confirmation !== input.password) errors.confirmation = "两次输入的密码不一致。";
  if (projectTitleLength < 1 || projectTitleLength > 200) errors.project_title = "作品名称必须为 1 至 200 个字符。";
  return errors;
}

function registrationFailure(code: string): SignupFormState {
  if (code === "REGISTRATION_EMAIL_CONFLICT") {
    return {
      ok: false,
      code,
      message: "这个邮箱已经注册，请直接登录或使用其他邮箱。",
      fieldErrors: { email: "该邮箱已被使用。" },
    };
  }
  if (code === "VALIDATION_FAILED") {
    return { ok: false, code, message: "提交内容未通过校验，请检查后重试。" };
  }
  if (code === "REGISTRATION_BACKEND_UNCONFIGURED" || code === "AUTH_BACKEND_UNCONFIGURED") {
    return { ok: false, code, message: "注册服务暂未配置，请联系网站管理员。" };
  }
  if (code === "INVALID_API_RESPONSE") {
    return { ok: false, code, message: "注册服务返回异常，请稍后重试。" };
  }
  return { ok: false, code, message: "暂时无法创建账号，请稍后重试。" };
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function rawStringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value : "";
}
