import type {
  CurrentUser,
  ProjectMembershipSummary,
  TenantMembershipSummary,
} from "@/lib/api/types";

/**
 * Client-side projections over the CurrentUser envelope.
 *
 * The Go control plane returns only a `role` string per tenant/project — it
 * does NOT send a capabilities object. We mirror the server-side role →
 * permission mapping (apps/api/internal/auth/auth.go) so the shell can decide
 * what to show. Enforcement still happens server-side on every request.
 */

/** Roles allowed to run the Writer agent / creative write (editor and above). */
const WRITER_ROLES = new Set(["project_owner", "owner", "admin", "editor", "writer"]);
/** Roles allowed to manage project assets. */
const ASSET_MANAGER_ROLES = new Set(["project_owner", "owner", "admin", "editor"]);
/** Tenant roles allowed to create a new novel (Go requireTenantManager). */
const TENANT_MANAGER_ROLES = new Set(["owner", "admin"]);

export function canWrite(role: string): boolean {
  return WRITER_ROLES.has(role);
}

export function canManageAssets(role: string): boolean {
  return ASSET_MANAGER_ROLES.has(role);
}

/** Whether this tenant membership can create novels via project admin. */
export function canManageTenant(role: string): boolean {
  return TENANT_MANAGER_ROLES.has(role);
}

/** Tenants where the user is owner/admin and may create a new novel. */
export function manageableTenants(currentUser: CurrentUser): TenantMembershipSummary[] {
  return currentUser.active_tenants.filter(
    (tenant) => tenant.status === "active" && canManageTenant(tenant.role),
  );
}

/** Human-facing label for a membership role. */
export function roleLabel(role: string): string {
  switch (role) {
    case "project_owner":
    case "owner":
      return "所有者";
    case "admin":
      return "管理员";
    case "editor":
      return "编辑";
    case "writer":
      return "作者";
    case "analyst":
      return "分析";
    case "viewer":
      return "只读";
    default:
      return role;
  }
}

/** A project paired with the tenant it belongs to, ready for display. */
export type ProjectWithTenant = ProjectMembershipSummary & {
  tenantName: string;
};

/**
 * Join each project against its tenant to recover the tenant's display name
 * (projects carry no `tenant_name` on the wire), then group by tenant,
 * preserving the API's ordering (tenants by name, projects by title).
 */
export function groupProjectsByTenant(
  currentUser: CurrentUser,
): Array<{ tenant: TenantMembershipSummary; projects: ProjectWithTenant[] }> {
  const tenantNameById = new Map<string, string>(
    currentUser.active_tenants.map((tenant) => [tenant.tenant_id, tenant.name]),
  );

  const projectsByTenant = new Map<string, ProjectWithTenant[]>();
  for (const project of currentUser.active_projects) {
    const withTenant: ProjectWithTenant = {
      ...project,
      tenantName: tenantNameById.get(project.tenant_id) ?? "未命名工作区",
    };
    const bucket = projectsByTenant.get(project.tenant_id);
    if (bucket) {
      bucket.push(withTenant);
    } else {
      projectsByTenant.set(project.tenant_id, [withTenant]);
    }
  }

  return currentUser.active_tenants
    .filter((tenant) => projectsByTenant.has(tenant.tenant_id))
    .map((tenant) => ({
      tenant,
      projects: projectsByTenant.get(tenant.tenant_id) ?? [],
    }));
}

/** Total project count across all tenants. */
export function projectCount(currentUser: CurrentUser): number {
  return currentUser.active_projects.length;
}

/** First character for the avatar monogram, falling back gracefully. */
export function avatarInitial(currentUser: CurrentUser): string {
  const source = currentUser.user.display_name || currentUser.user.email || "?";
  return Array.from(source.trim())[0]?.toUpperCase() ?? "?";
}
