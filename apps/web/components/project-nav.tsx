"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CurrentUserSummary, ProjectMembershipSummary, TenantMembershipSummary } from "../lib/api";

const navItems = [
  { label: "Overview", path: "/overview" },
  { label: "Assets", path: "/assets" },
  { label: "Story Graph", path: "/graph" },
  { label: "Worldline", path: "/worldline" },
  { label: "Character Console", path: "/character-console" },
  { label: "Writer", path: "/writer" },
  { label: "LLM Facility", path: "/llm-facility" },
  { label: "Guide", path: "/guide" },
];

type ProjectNavProps = {
  basePath: string;
  currentUser: CurrentUserSummary;
  logoutAction: () => Promise<void>;
  tenantSlug: string;
  projectId: string;
};

export function ProjectNav({ basePath, currentUser, logoutAction, tenantSlug, projectId }: ProjectNavProps) {
  const pathname = usePathname();
  const activeProjects = currentUser.ok ? currentUser.active_projects : [];
  const routeTenantProjects = activeProjects.filter((project) => project.tenant_id === tenantSlug);
  const currentProject = routeTenantProjects.find((project) => project.project_id === projectId);
  const currentSectionPath = navItems.find((item) => pathname === `${basePath}${item.path}`)?.path ?? "/overview";

  return (
    <div className="sidebar-stack">
      <section className="sidebar-section" aria-label="User">
        <p className="eyebrow">User</p>
        {currentUser.ok ? (
          <>
            <h2>{currentUser.display_name || currentUser.email || currentUser.user_id}</h2>
            <p>{currentUser.email || currentUser.user_id}</p>
          </>
        ) : (
          <div className="panel error-box">
            <strong>Membership unavailable</strong>
            <p>{currentUser.code}</p>
            <p>{currentUser.message}</p>
          </div>
        )}
        <form action={logoutAction}>
          <button className="nav-link nav-button" type="submit">
            Sign out
          </button>
        </form>
      </section>

      <section className="sidebar-section" aria-label="Tenants">
        <p className="eyebrow">Tenants</p>
        {currentUser.ok ? (
          <div className="nav-list">
            {currentUser.active_tenants.map((tenant) => (
              <TenantChoice
                activeProjects={activeProjects}
                currentSectionPath={currentSectionPath}
                key={tenant.tenant_id}
                projectId={projectId}
                tenant={tenant}
                tenantSlug={tenantSlug}
              />
            ))}
          </div>
        ) : null}
      </section>

      <section className="sidebar-section" aria-label="Projects">
        <p className="eyebrow">Projects</p>
        {currentUser.ok ? (
          <div className="nav-list">
            {routeTenantProjects.map((project) => {
              const href = hrefForProject(project.tenant_id, project.project_id, currentSectionPath);
              return (
                <Link
                  aria-current={project.project_id === projectId ? "page" : undefined}
                  className="nav-link"
                  href={href}
                  key={project.project_id}
                >
                  {project.name}
                </Link>
              );
            })}
          </div>
        ) : null}
      </section>

      <section className="sidebar-section" aria-label="Project sections">
        <p className="eyebrow">Project</p>
        <h2>{tenantSlug}</h2>
        <p>Project: {projectId}</p>
        {currentProject ? (
          <nav className="nav-list">
            {navItems.map((item) => {
              const href = `${basePath}${item.path}`;
              return (
                <Link
                  aria-current={pathname === href ? "page" : undefined}
                  className="nav-link"
                  href={href}
                  key={item.path}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        ) : (
          <div className="panel error-box">
            <strong>Project access unavailable</strong>
            <p>ACTIVE_PROJECT_MEMBERSHIP_MISSING</p>
            <p>The current user does not have an active membership for this project.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function TenantChoice({
  activeProjects,
  currentSectionPath,
  projectId,
  tenant,
  tenantSlug,
}: {
  activeProjects: ProjectMembershipSummary[];
  currentSectionPath: string;
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

  const href = hrefForProject(tenant.tenant_id, project.project_id, currentSectionPath);
  return (
    <Link
      aria-current={tenant.tenant_id === tenantSlug && project.project_id === projectId ? "page" : undefined}
      className="nav-link"
      href={href}
    >
      {tenant.name}
    </Link>
  );
}

function hrefForProject(tenantId: string, projectId: string, sectionPath: string) {
  return `/${tenantId}/projects/${projectId}${sectionPath}`;
}
