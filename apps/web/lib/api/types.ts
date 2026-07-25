/**
 * Wire types mirroring the Go control plane's `auth.CurrentUser`
 * (apps/api/internal/auth/auth.go). These are the exact JSON shapes returned
 * by `GET /v1/me` — field names are snake_case as they appear on the wire.
 *
 * Note: a project's display title is exposed as `name` (not `title`), and a
 * project carries no `tenant_name` — resolve the tenant's display name by
 * joining `project.tenant_id` against `active_tenants[].tenant_id`.
 */

export type UserSummary = {
  user_id: string;
  email: string;
  display_name: string;
  avatar_url: string;
};

export type TenantMembershipSummary = {
  tenant_id: string;
  name: string;
  role: string;
  status: string;
};

export type ProjectMembershipSummary = {
  tenant_id: string;
  project_id: string;
  name: string;
  role: string;
  status: string;
};

export type CurrentUser = {
  user: UserSummary;
  active_tenants: TenantMembershipSummary[];
  active_projects: ProjectMembershipSummary[];
};
