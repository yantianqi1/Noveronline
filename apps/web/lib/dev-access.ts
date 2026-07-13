/**
 * Development-only login bypass helpers.
 *
 * Disabled by default so every normal entry uses the real password/session flow.
 * Local harnesses may opt in explicitly. Production mode always disables the
 * bypass, even when a stale deployment environment still sets the flag.
 */

const DEFAULT_DEV_ACTOR_USER_ID = "10000000-0000-0000-0000-000000000001";
const DEFAULT_DEV_TENANT_ID = "10000000-0000-0000-0000-000000000101";
const DEFAULT_DEV_PROJECT_ID = "10000000-0000-0000-0000-000000000201";

export function isDevLoginBypassEnabled(): boolean {
  if (process.env.NODE_ENV === "production") {
    return false;
  }
  const flag = process.env.MIROFISH_WEB_DEV_BYPASS_LOGIN?.trim().toLowerCase();
  if (flag === "0" || flag === "false" || flag === "off" || flag === "no") {
    return false;
  }
  if (flag === "1" || flag === "true" || flag === "on" || flag === "yes") {
    return true;
  }
  return false;
}

export function devActorUserId(): string | undefined {
  const configured = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim();
  if (configured) {
    return configured;
  }
  if (isDevLoginBypassEnabled()) {
    return DEFAULT_DEV_ACTOR_USER_ID;
  }
  return undefined;
}

export function devWorkspacePath(section = "overview"): string {
  const tenantId = process.env.MIROFISH_WEB_DEV_TENANT_ID?.trim() || DEFAULT_DEV_TENANT_ID;
  const projectId = process.env.MIROFISH_WEB_DEV_PROJECT_ID?.trim() || DEFAULT_DEV_PROJECT_ID;
  const normalizedSection = section.replace(/^\/+|\/+$/g, "") || "overview";
  return `/${tenantId}/projects/${projectId}/${normalizedSection}`;
}

export function devEntryRedirectPath(): string {
  return isDevLoginBypassEnabled() ? devWorkspacePath("overview") : "/login";
}
