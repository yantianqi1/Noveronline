"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, useTransition } from "react";
import {
  BookOpenText,
  Cpu,
  KeyRound,
  LogOut,
  MoreHorizontal,
  X,
} from "lucide-react";

import { Bi } from "./bilingual-text";
import { LanguageSwitcher } from "./language-switcher";
import { NovelSwitcher } from "./novel-switcher";
import type { ProjectActionState } from "../app/(app)/[tenantSlug]/projects/[projectId]/project-actions";
import {
  signalWorkspaceNavigationComplete,
  signalWorkspaceNavigationStart,
} from "./workspace-route-transition";
import type { CurrentUserSummary } from "../lib/api";
import { matchesWorkspaceNavigationPath, workspacePathForProject } from "../lib/workspace-route";

type ProjectActionHandler = (state: ProjectActionState, formData: FormData) => Promise<ProjectActionState>;

type MobileTopBarProps = {
  tenantSlug: string;
  projectId: string;
  currentUser: CurrentUserSummary;
  changePasswordHref: string;
  createProjectAction: ProjectActionHandler;
  renameProjectAction: ProjectActionHandler;
  logoutAction: () => Promise<void>;
};

export function MobileTopBar({
  tenantSlug,
  projectId,
  currentUser,
  changePasswordHref,
  createProjectAction,
  renameProjectAction,
  logoutAction,
}: MobileTopBarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const sheetId = useId();
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [, startTransition] = useTransition();

  const activeTenants = currentUser.ok ? currentUser.active_tenants : [];
  const hasMultipleWorkspaces = activeTenants.length > 1;
  const activeProjects = currentUser.ok ? currentUser.active_projects : [];
  const routeTenantProjects = activeProjects.filter((project) => project.tenant_id === tenantSlug);
  const currentProject = routeTenantProjects.find((project) => project.project_id === projectId);
  const currentTenant = currentUser.ok
    ? currentUser.active_tenants.find((tenant) => tenant.tenant_id === tenantSlug)
    : undefined;
  const sectionPath = currentProject
    ? detectSectionPath(pathname, activeTenants, currentProject)
    : "/overview";
  const overviewHref = currentProject
    ? workspacePathForProject(activeTenants, currentProject, "/overview")
    : `/${tenantSlug}/projects/${projectId}/overview`;
  const llmHref = currentProject
    ? workspacePathForProject(activeTenants, currentProject, "/llm-facility")
    : `/${tenantSlug}/projects/${projectId}/llm-facility`;
  const meHref = currentProject
    ? workspacePathForProject(activeTenants, currentProject, "/me")
    : `/${tenantSlug}/projects/${projectId}/me`;

  const closeMore = useCallback(() => {
    setMoreOpen(false);
    moreButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!moreOpen) {
      return;
    }
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMore();
      }
    };
    document.addEventListener("keydown", onKey);
    const first = sheetRef.current?.querySelector<HTMLElement>("a, button, [tabindex]:not([tabindex=\"-1\"])");
    first?.focus();
    return () => {
      root.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
  }, [moreOpen, closeMore]);

  useEffect(() => {
    const immersive = pathname.includes("/writer");
    const frame = document.querySelector(".app-frame.app-frame-unified");
    if (frame instanceof HTMLElement) {
      frame.dataset.mobileImmersive = immersive ? "true" : "false";
    }
    return () => {
      if (frame instanceof HTMLElement) {
        delete frame.dataset.mobileImmersive;
      }
    };
  }, [pathname]);

  function navigateTo(event: { preventDefault: () => void }, href: string) {
    event.preventDefault();
    setMoreOpen(false);
    if (href === pathname) {
      return;
    }
    signalWorkspaceNavigationStart();
    startTransition(() => {
      router.push(href);
      signalWorkspaceNavigationComplete();
    });
  }

  return (
    <>
      <header className="mobile-topbar">
        {currentProject ? (
          <div className="mobile-topbar-switcher">
            <NovelSwitcher
              createAction={createProjectAction}
              currentName={currentProject.name}
              currentProjectId={currentProject.project_id}
              novels={routeTenantProjects.map((project) => ({
                projectId: project.project_id,
                name: project.name,
                href: workspacePathForProject(activeTenants, project, sectionPath),
              }))}
              onSwitch={navigateTo}
              renameAction={renameProjectAction}
              workspaceLabel={
                hasMultipleWorkspaces
                  ? currentTenant?.name || <Bi zh="当前工作区" en="Current workspace" />
                  : <Bi zh="我的工作区" en="My workspace" />
              }
            />
          </div>
        ) : (
          <Link className="mobile-topbar-brand" href={overviewHref}>
            <span className="mobile-topbar-mark" aria-hidden="true">
              <BookOpenText size={18} strokeWidth={1.8} />
            </span>
            <span className="mobile-topbar-copy">
              <strong>MiroFish Novel</strong>
              <small><Bi zh="创作工作台" en="Creative workspace" /></small>
            </span>
          </Link>
        )}

        <div className="mobile-topbar-actions">
          <LanguageSwitcher />
          <button
            aria-controls={sheetId}
            aria-expanded={moreOpen}
            aria-label={moreOpen ? "关闭更多 / Close more" : "更多 / More"}
            className="mobile-topbar-icon-btn"
            onClick={() => setMoreOpen((open) => !open)}
            ref={moreButtonRef}
            type="button"
          >
            {moreOpen ? <X aria-hidden="true" size={20} /> : <MoreHorizontal aria-hidden="true" size={20} />}
          </button>
        </div>
      </header>

      <button
        aria-hidden="true"
        className="mobile-more-backdrop"
        data-open={moreOpen ? "true" : "false"}
        onClick={closeMore}
        tabIndex={-1}
        type="button"
      />

      <div
        aria-hidden={!moreOpen}
        aria-label="更多操作 / More actions"
        className="mobile-more-sheet"
        data-open={moreOpen ? "true" : "false"}
        id={sheetId}
        ref={sheetRef}
        role="dialog"
      >
        <div className="mobile-more-handle" aria-hidden="true" />
        <h2 className="mobile-more-title"><Bi zh="更多" en="More" /></h2>
        <div className="mobile-more-list">
          <Link
            className="mobile-more-link"
            href={meHref}
            onNavigate={(event) => navigateTo(event, meHref)}
          >
            <BookOpenText aria-hidden="true" size={18} />
            <span>
              <strong><Bi zh="我的主页" en="My page" /></strong>
              <small><Bi zh="账户与设置入口" en="Account and settings" /></small>
            </span>
          </Link>
          <Link
            className="mobile-more-link"
            href={llmHref}
            onNavigate={(event) => navigateTo(event, llmHref)}
          >
            <Cpu aria-hidden="true" size={18} />
            <span>
              <strong><Bi zh="模型设置" en="Model settings" /></strong>
              <small><Bi zh="绑定模块与通道" en="Bindings and channels" /></small>
            </span>
          </Link>
          <Link
            className="mobile-more-link"
            href={changePasswordHref}
            onNavigate={(event) => navigateTo(event, changePasswordHref)}
          >
            <KeyRound aria-hidden="true" size={18} />
            <span>
              <strong><Bi zh="修改密码" en="Change password" /></strong>
              <small><Bi zh="账户安全" en="Account security" /></small>
            </span>
          </Link>
          <form action={logoutAction}>
            <button className="mobile-more-action" data-tone="danger" type="submit">
              <LogOut aria-hidden="true" size={18} />
              <span>
                <strong><Bi zh="退出登录" en="Sign out" /></strong>
                <small><Bi zh="结束当前会话" en="End this session" /></small>
              </span>
            </button>
          </form>
        </div>
      </div>
    </>
  );
}

function detectSectionPath(
  pathname: string,
  tenants: { tenant_id: string; name: string }[],
  project: { tenant_id: string; project_id: string; name: string },
) {
  const sections = [
    "/overview",
    "/materials",
    "/assets",
    "/graph",
    "/worldline",
    "/character-console",
    "/writer",
    "/me",
    "/llm-facility",
    "/security",
  ];
  for (const section of sections) {
    const href = workspacePathForProject(tenants, project, section);
    if (matchesWorkspaceNavigationPath(pathname, href, section)) {
      return section;
    }
  }
  return "/overview";
}
