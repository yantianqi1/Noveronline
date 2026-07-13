"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition, type SyntheticEvent } from "react";
import {
  BookOpenText,
  Boxes,
  Building2,
  Cpu,
  FolderKanban,
  GitBranch,
  LayoutDashboard,
  KeyRound,
  LogOut,
  Menu,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  PenLine,
  RefreshCw,
  ShieldOff,
  UsersRound,
  X,
} from "lucide-react";
import { Bi, FailureText, StatusValue } from "./bilingual-text";
import { LanguageSwitcher } from "./language-switcher";
import {
  signalWorkspaceNavigationComplete,
  signalWorkspaceNavigationStart,
} from "./workspace-route-transition";
import type {
  CurrentUserSessionsSummary,
  CurrentUserSummary,
  ProjectMembershipSummary,
  TenantMembershipSummary,
} from "../lib/api";
import { workspacePathForProject } from "../lib/workspace-route";

const creativeNavItems = [
  { label: "Overview", zh: "项目总览", path: "/overview", icon: LayoutDashboard },
  { label: "Assets", zh: "资产库", path: "/assets", icon: Boxes },
  { label: "Story Graph", zh: "故事图谱", path: "/graph", icon: Network },
  { label: "Worldline", zh: "世界线", path: "/worldline", icon: GitBranch },
  { label: "Characters", zh: "角色", path: "/character-console", icon: UsersRound },
  { label: "Writer", zh: "写作台", path: "/writer", icon: PenLine },
];

const settingsNavItems = [
  { label: "Model settings", zh: "模型设置", path: "/llm-facility", icon: Cpu },
];

const navItems = [...creativeNavItems, ...settingsNavItems];

type ProjectNavProps = {
  basePath: string;
  changePasswordHref: string;
  currentUser: CurrentUserSummary;
  logoutAction: () => Promise<void>;
  revokeAllSessionsAction: () => Promise<void>;
  revokeTenantSessionsAction: () => Promise<void>;
  rotateSessionAction: () => Promise<void>;
  tenantSlug: string;
  projectId: string;
};

type WorkspaceNavigationEvent = {
  preventDefault: () => void;
};

export function ProjectNav({
  basePath: _basePath,
  changePasswordHref,
  currentUser,
  logoutAction,
  revokeAllSessionsAction,
  revokeTenantSessionsAction,
  rotateSessionAction,
  tenantSlug,
  projectId,
}: ProjectNavProps) {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const navToggleRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const [optimisticHref, setOptimisticHref] = useState<string | null>(null);
  const [currentUserSessions, setCurrentUserSessions] = useState<CurrentUserSessionsSummary>();
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [isNavigationPending, startNavigationTransition] = useTransition();
  const pathname = usePathname();
  const router = useRouter();
  const activeHref = optimisticHref ?? pathname;
  const activeTenants = currentUser.ok ? currentUser.active_tenants : [];
  const hasMultipleWorkspaces = activeTenants.length > 1;
  const activeProjects = currentUser.ok ? currentUser.active_projects : [];
  const routeTenantProjects = activeProjects.filter((project) => project.tenant_id === tenantSlug);
  const currentProject = routeTenantProjects.find((project) => project.project_id === projectId);
  const currentSectionPath = currentProject && currentUser.ok
    ? navItems.find((item) => (
        matchesNavigationHref(
          pathname,
          workspacePathForProject(activeTenants, currentProject, item.path),
          item.path,
        )
      ))?.path ?? "/overview"
    : "/overview";
  const currentTenant = currentUser.ok ? currentUser.active_tenants.find((tenant) => tenant.tenant_id === tenantSlug) : undefined;
  const canManageTenantSessions = currentTenant ? ["owner", "admin"].includes(currentTenant.role) : false;
  const userLabel = currentUser.ok
    ? currentUser.display_name || currentUser.email || "MiroFish user"
    : "MiroFish user";

  useEffect(() => {
    setOptimisticHref(null);
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);

  useEffect(() => {
    const collapsed = window.localStorage.getItem("mirofish-sidebar-collapsed") === "true";
    setSidebarCollapsed(collapsed);
    document.documentElement.dataset.sidebarCollapsed = collapsed ? "true" : "false";
    return () => {
      delete document.documentElement.dataset.sidebarCollapsed;
    };
  }, []);

  function toggleSidebar() {
    const collapsed = !sidebarCollapsed;
    setSidebarCollapsed(collapsed);
    window.localStorage.setItem("mirofish-sidebar-collapsed", String(collapsed));
    document.documentElement.dataset.sidebarCollapsed = collapsed ? "true" : "false";
  }

  const closeNavigation = useCallback(() => {
    setNavigationOpen(false);
    navToggleRef.current?.focus();
  }, []);

  // Mobile drawer: lock page scroll (via the root element), close on Escape,
  // and move focus into the panel while it is open. Desktop never opens this
  // state because the trigger is hidden at that breakpoint.
  useEffect(() => {
    if (!navigationOpen) {
      return;
    }
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeNavigation();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    const firstFocusable = drawerRef.current?.querySelector<HTMLElement>(
      'a, button, [tabindex]:not([tabindex="-1"])',
    );
    firstFocusable?.focus();
    return () => {
      root.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [navigationOpen, closeNavigation]);

  useEffect(() => {
    if (!isNavigationPending) {
      signalWorkspaceNavigationComplete();
    }
  }, [isNavigationPending]);

  function beginNavigation(href: string) {
    setNavigationOpen(false);
    if (href !== pathname) {
      setOptimisticHref(href);
      signalWorkspaceNavigationStart();
    }
  }

  function prefetchRoute(href: string) {
    if (href !== pathname) router.prefetch(href);
  }

  function navigateWorkspace(event: WorkspaceNavigationEvent, href: string) {
    event.preventDefault();
    if (href === pathname) {
      return;
    }
    beginNavigation(href);
    startNavigationTransition(() => router.push(href));
  }

  async function loadSessionsWhenOpened(event: SyntheticEvent<HTMLDetailsElement>) {
    if (!event.currentTarget.open || currentUserSessions || sessionsLoading) {
      return;
    }
    setSessionsLoading(true);
    try {
      const response = await fetch("/api/auth/sessions", {
        cache: "no-store",
        credentials: "same-origin",
      });
      const payload = await response.json() as CurrentUserSessionsSummary;
      setCurrentUserSessions(payload);
    } catch {
      setCurrentUserSessions({
        ok: false,
        code: "SESSION_LIST_FAILED",
        message: "session list failed",
        request_id: "",
      });
    } finally {
      setSessionsLoading(false);
    }
  }

  return (
    <div className="sidebar-stack">
      <div className="sidebar-top-row">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <BookOpenText size={22} strokeWidth={1.7} />
          </span>
          <span className="brand-copy">
            <strong>MiroFish Novel</strong>
            <small><Bi zh="创作控制中枢" en="Creative control center" /></small>
          </span>
        </div>
        <div className="sidebar-top-actions">
          <LanguageSwitcher />
          <button
            aria-expanded={!sidebarCollapsed}
            aria-label={sidebarCollapsed ? "展开侧边栏 / Expand sidebar" : "折叠侧边栏 / Collapse sidebar"}
            className="desktop-sidebar-toggle"
            onClick={toggleSidebar}
            title={sidebarCollapsed ? "展开侧边栏 / Expand sidebar" : "折叠侧边栏 / Collapse sidebar"}
            type="button"
          >
            {sidebarCollapsed ? <PanelLeftOpen aria-hidden="true" size={19} /> : <PanelLeftClose aria-hidden="true" size={19} />}
          </button>
          <button
            aria-controls="project-nav-drawer"
            aria-expanded={navigationOpen}
            aria-label={navigationOpen ? "关闭导航 / Close navigation" : "打开导航 / Open navigation"}
            className="mobile-nav-toggle"
            onClick={() => setNavigationOpen((open) => !open)}
            ref={navToggleRef}
            title={navigationOpen ? "关闭导航 / Close navigation" : "打开导航 / Open navigation"}
            type="button"
          >
            {navigationOpen ? <X aria-hidden="true" size={20} /> : <Menu aria-hidden="true" size={20} />}
          </button>
        </div>
      </div>

      <button
        aria-hidden="true"
        className="sidebar-nav-backdrop"
        data-open={navigationOpen ? "true" : "false"}
        onClick={closeNavigation}
        tabIndex={-1}
        type="button"
      />

      <div
        className="sidebar-drawer"
        data-open={navigationOpen ? "true" : "false"}
        id="project-nav-drawer"
        ref={drawerRef}
      >
        <section className="sidebar-section sidebar-primary-nav" aria-label="Project sections / 项目导航">
          <div className="project-context">
            <span className="project-context-icon" aria-hidden="true">
              <FolderKanban size={17} strokeWidth={1.8} />
            </span>
            <span>
              <strong>{currentProject?.name || <Bi zh="当前项目" en="Current project" />}</strong>
              <small>
                {hasMultipleWorkspaces
                  ? currentTenant?.name || <Bi zh="当前工作区" en="Current workspace" />
                  : <Bi zh="我的工作区" en="My workspace" />}
              </small>
            </span>
          </div>
          {currentProject ? (
            <nav className="nav-list" aria-label="创作流程 / Creative workflow">
              <p className="nav-group-label"><Bi zh="创作流程" en="Creative workflow" /></p>
              <NavigationLinks
                activeHref={activeHref}
                activeTenants={activeTenants}
                currentProject={currentProject}
                items={creativeNavItems}
                onFocus={prefetchRoute}
                onNavigate={navigateWorkspace}
              />
            </nav>
          ) : (
            <div className="panel error-box">
              <strong><Bi zh="项目访问不可用" en="Project access unavailable" /></strong>
              <p><Bi zh="当前用户没有该项目的有效成员权限。" en="The current user does not have an active membership for this project." /></p>
            </div>
          )}
        </section>

        {hasMultipleWorkspaces ? (
          <details className="sidebar-disclosure">
            <summary>
              <Building2 aria-hidden="true" size={16} />
              <Bi zh="切换工作区" en="Switch workspace" />
            </summary>
            <section className="sidebar-section" aria-label="Workspaces / 工作区">
              <p className="eyebrow"><Bi zh="工作区" en="Workspaces" /></p>
              <div className="nav-list">
                {activeTenants.map((tenant) => (
                  <TenantChoice
                    activeProjects={activeProjects}
                    currentSectionPath={currentSectionPath}
                    key={tenant.tenant_id}
                    onNavigate={navigateWorkspace}
                    projectId={projectId}
                    tenant={tenant}
                    tenantSlug={tenantSlug}
                  />
                ))}
              </div>
            </section>

            <ProjectChoices
              activeTenants={activeTenants}
              currentSectionPath={currentSectionPath}
              onNavigate={navigateWorkspace}
              projectId={projectId}
              projects={routeTenantProjects}
            />
          </details>
        ) : routeTenantProjects.length > 1 ? (
          <details className="sidebar-disclosure">
            <summary>
              <FolderKanban aria-hidden="true" size={16} />
              <Bi zh="切换项目" en="Switch project" />
            </summary>
            <ProjectChoices
              activeTenants={activeTenants}
              currentSectionPath={currentSectionPath}
              onNavigate={navigateWorkspace}
              projectId={projectId}
              projects={routeTenantProjects}
            />
          </details>
        ) : null}

        {currentProject ? (
          <details className="sidebar-disclosure sidebar-settings" open={settingsNavItems.some((item) => matchesNavigationHref(pathname, workspacePathForProject(activeTenants, currentProject, item.path), item.path))}>
            <summary>
              <Cpu aria-hidden="true" size={16} />
              <Bi zh="项目设置" en="Project settings" />
            </summary>
            <nav className="sidebar-section nav-list" aria-label="项目设置 / Project settings">
              <NavigationLinks
                activeHref={activeHref}
                activeTenants={activeTenants}
                currentProject={currentProject}
                items={settingsNavItems}
                onFocus={prefetchRoute}
                onNavigate={navigateWorkspace}
              />
            </nav>
          </details>
        ) : null}

        <details className="sidebar-disclosure sidebar-account-menu">
          <summary className="account-summary">
            <span className="account-avatar" aria-hidden="true">
              {userLabel.slice(0, 1).toUpperCase()}
            </span>
            <span>
              <strong>{userLabel}</strong>
              <small><Bi zh="账户与会话" en="Account and sessions" /></small>
            </span>
          </summary>
          <section className="sidebar-section sidebar-account" aria-label="User / 用户">
          {currentUser.ok ? (
            <div className="account-summary account-summary-detail">
              <span className="account-avatar" aria-hidden="true">
                {userLabel.slice(0, 1).toUpperCase()}
              </span>
              <span>
                <strong>{userLabel}</strong>
                <small>{currentUser.email || <Bi zh="已登录账户" en="Signed-in account" />}</small>
              </span>
            </div>
          ) : (
            <div className="panel error-box">
              <strong><Bi zh="成员信息不可用" en="Membership unavailable" /></strong>
              <p><FailureText /></p>
            </div>
          )}
          <div className="account-actions">
            <form action={rotateSessionAction}>
              <button className="nav-link nav-button" type="submit">
                <RefreshCw aria-hidden="true" size={16} />
                <Bi zh="刷新会话" en="Refresh session" />
              </button>
            </form>
            <form action={logoutAction}>
              <button className="nav-link nav-button" type="submit">
                <LogOut aria-hidden="true" size={16} />
                <Bi zh="退出登录" en="Sign out" />
              </button>
            </form>
          </div>
          <Link className="nav-link nav-button" href={changePasswordHref} onNavigate={(event) => navigateWorkspace(event, changePasswordHref)}>
            <KeyRound aria-hidden="true" size={16} />
            <Bi zh="账户安全" en="Account security" />
          </Link>
          </section>

        <details className="sidebar-disclosure sidebar-sessions" onToggle={loadSessionsWhenOpened}>
          <summary><Bi zh="活跃会话" en="Active sessions" /></summary>
          <section className="sidebar-section" aria-label="会话 / Sessions">
            {sessionsLoading ? (
              <p aria-live="polite"><Bi zh="正在加载..." en="Loading..." /></p>
            ) : currentUserSessions?.ok ? (
              <div className="nav-list session-list">
                {currentUserSessions.sessions.map((session) => (
                  <div className="nav-link" key={session.session_id}>
                    <strong>{session.current ? <Bi zh="当前会话" en="Current" /> : <StatusValue value={session.status} />}</strong>
                    <span><Bi zh="到期" en="Expires" /> {formatSessionTimestamp(session.expires_at)}</span>
                    <span><Bi zh="最近活动" en="Last seen" /> {formatSessionTimestamp(session.last_seen_at)}</span>
                  </div>
                ))}
              </div>
            ) : currentUserSessions ? (
              <div className="panel error-box">
                <strong><Bi zh="会话信息不可用" en="Sessions unavailable" /></strong>
                <p><FailureText /></p>
              </div>
            ) : null}
            <form action={revokeAllSessionsAction}>
              <button className="nav-link nav-button" type="submit">
                <ShieldOff aria-hidden="true" size={16} />
                <Bi zh="退出所有设备" en="Sign out everywhere" />
              </button>
            </form>
            {canManageTenantSessions ? (
              <form action={revokeTenantSessionsAction}>
                <button className="nav-link nav-button danger-nav-button" type="submit">
                  <ShieldOff aria-hidden="true" size={16} />
                  <Bi zh="撤销工作区会话" en="Revoke workspace sessions" />
                </button>
              </form>
            ) : null}
          </section>
        </details>
        </details>
      </div>

    </div>
  );
}

function NavigationLinks({
  activeHref,
  activeTenants,
  currentProject,
  items,
  onFocus,
  onNavigate,
}: {
  activeHref: string;
  activeTenants: TenantMembershipSummary[];
  currentProject: ProjectMembershipSummary;
  items: typeof navItems;
  onFocus: (href: string) => void;
  onNavigate: (event: WorkspaceNavigationEvent, href: string) => void;
}) {
  return items.map((item) => {
    const href = workspacePathForProject(activeTenants, currentProject, item.path);
    const active = matchesNavigationHref(activeHref, href, item.path);
    const Icon = item.icon;
    return (
      <Link
        aria-current={active ? "page" : undefined}
        className="nav-link"
        data-active={active ? "true" : undefined}
        href={href}
        key={item.path}
        onFocus={() => onFocus(href)}
        onMouseEnter={() => onFocus(href)}
        onNavigate={(event) => onNavigate(event, href)}
      >
        <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
        <Bi zh={item.zh} en={item.label} />
      </Link>
    );
  });
}

function matchesNavigationHref(pathname: string, href: string, sectionPath: string) {
  return pathname === href || (sectionPath !== "/overview" && pathname.startsWith(`${href}/`));
}

function ProjectChoices({
  activeTenants,
  currentSectionPath,
  onNavigate,
  projectId,
  projects,
}: {
  activeTenants: TenantMembershipSummary[];
  currentSectionPath: string;
  onNavigate: (event: WorkspaceNavigationEvent, href: string) => void;
  projectId: string;
  projects: ProjectMembershipSummary[];
}) {
  return (
    <section className="sidebar-section" aria-label="Projects / 项目">
      <p className="eyebrow"><Bi zh="项目" en="Projects" /></p>
      <div className="nav-list">
        {projects.map((project) => {
          const href = workspacePathForProject(activeTenants, project, currentSectionPath);
          return (
            <Link
              aria-current={project.project_id === projectId ? "page" : undefined}
              className="nav-link"
              href={href}
              key={project.project_id}
              onNavigate={(event) => onNavigate(event, href)}
            >
              <FolderKanban aria-hidden="true" size={16} />
              {project.name}
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function TenantChoice({
  activeProjects,
  currentSectionPath,
  onNavigate,
  projectId,
  tenant,
  tenantSlug,
}: {
  activeProjects: ProjectMembershipSummary[];
  currentSectionPath: string;
  onNavigate: (event: WorkspaceNavigationEvent, href: string) => void;
  projectId: string;
  tenant: TenantMembershipSummary;
  tenantSlug: string;
}) {
  const project = activeProjects.find((item) => item.tenant_id === tenant.tenant_id);
  if (!project) {
    return (
      <span className="nav-link" aria-current={tenant.tenant_id === tenantSlug ? "page" : undefined}>
        {tenant.name}
      </span>
    );
  }

  const href = workspacePathForProject([tenant], project, currentSectionPath);
  return (
    <Link
      aria-current={tenant.tenant_id === tenantSlug && project.project_id === projectId ? "page" : undefined}
      className="nav-link"
      href={href}
      onNavigate={(event) => onNavigate(event, href)}
    >
      <Building2 aria-hidden="true" size={16} />
      {tenant.name}
    </Link>
  );
}

function formatSessionTimestamp(value: string) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(date);
}
