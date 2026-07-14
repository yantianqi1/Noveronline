import Link from "next/link";
import { ChevronRight, Cpu, KeyRound, LogOut, Shield } from "lucide-react";

import { Bi } from "./bilingual-text";
import type { CurrentUserSummary } from "../lib/api";

type MeHubProps = {
  currentUser: CurrentUserSummary;
  changePasswordHref: string;
  llmHref: string;
  securityHref: string;
  logoutAction: () => Promise<void>;
};

export function MeHub({
  currentUser,
  changePasswordHref,
  llmHref,
  securityHref,
  logoutAction,
}: MeHubProps) {
  const displayName = currentUser.ok
    ? currentUser.display_name || currentUser.email || "MiroFish user"
    : "MiroFish user";
  const email = currentUser.ok ? currentUser.email || "—" : "—";
  const initial = displayName.trim().slice(0, 1).toUpperCase() || "M";

  return (
    <div className="mobile-hub me-hub">
      <header className="mobile-hub-hero mobile-layer" data-layer="hero">
        <p className="eyebrow"><Bi zh="我的" en="Me" /></p>
        <div className="mobile-profile-hero">
          <span aria-hidden="true" className="mobile-profile-avatar">
            {initial}
          </span>
          <div className="mobile-profile-copy">
            <h1>{displayName}</h1>
            <p>
              <Bi
                zh="管理账户、模型绑定与会话安全。"
                en="Manage account, model bindings, and session security."
              />
            </p>
          </div>
        </div>
      </header>

      <section
        aria-labelledby="me-account-heading"
        className="mobile-hub-section mobile-layer mobile-profile-card"
        data-layer="card"
      >
        <h2 id="me-account-heading"><Bi zh="账户" en="Account" /></h2>
        <dl className="mobile-hub-meta">
          <div>
            <dt><Bi zh="显示名" en="Display name" /></dt>
            <dd>{displayName}</dd>
          </div>
          <div>
            <dt><Bi zh="邮箱" en="Email" /></dt>
            <dd>{email}</dd>
          </div>
        </dl>
      </section>

      <section
        aria-label="设置 / Settings"
        className="mobile-paper-stack mobile-layer"
        data-layer="stack"
      >
        <Link className="mobile-hub-card mobile-stack-row" href={llmHref} style={{ ["--stack-index" as string]: "0" }}>
          <span className="mobile-hub-card-icon" aria-hidden="true">
            <Cpu size={22} strokeWidth={1.8} />
          </span>
          <span className="mobile-hub-card-body">
            <strong><Bi zh="模型设置" en="Model settings" /></strong>
            <small><Bi zh="模块绑定、通道与额度" en="Bindings, channels, and quotas" /></small>
          </span>
          <ChevronRight aria-hidden="true" className="mobile-hub-card-chevron" size={18} />
        </Link>

        <Link
          className="mobile-hub-card mobile-stack-row"
          href={changePasswordHref}
          style={{ ["--stack-index" as string]: "1" }}
        >
          <span className="mobile-hub-card-icon" aria-hidden="true">
            <KeyRound size={22} strokeWidth={1.8} />
          </span>
          <span className="mobile-hub-card-body">
            <strong><Bi zh="修改密码" en="Change password" /></strong>
            <small><Bi zh="更新登录凭据" en="Update sign-in credentials" /></small>
          </span>
          <ChevronRight aria-hidden="true" className="mobile-hub-card-chevron" size={18} />
        </Link>

        <Link
          className="mobile-hub-card mobile-stack-row"
          href={securityHref}
          style={{ ["--stack-index" as string]: "2" }}
        >
          <span className="mobile-hub-card-icon" aria-hidden="true">
            <Shield size={22} strokeWidth={1.8} />
          </span>
          <span className="mobile-hub-card-body">
            <strong><Bi zh="安全与会话" en="Security and sessions" /></strong>
            <small><Bi zh="查看与撤销登录会话" en="Review and revoke sessions" /></small>
          </span>
          <ChevronRight aria-hidden="true" className="mobile-hub-card-chevron" size={18} />
        </Link>
      </section>

      <form action={logoutAction} className="mobile-layer" data-layer="footer">
        <button className="mobile-logout-btn" type="submit">
          <LogOut aria-hidden="true" size={18} />
          <span>
            <strong><Bi zh="退出登录" en="Sign out" /></strong>
            <small><Bi zh="结束当前会话" en="End this session" /></small>
          </span>
        </button>
      </form>
    </div>
  );
}
