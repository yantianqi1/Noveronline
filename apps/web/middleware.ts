import { NextRequest, NextResponse } from "next/server";

import {
  canonicalLLMFacilitySearch,
  DEFAULT_LLM_MODULE_KEY,
  llmModuleKeyFromPathSegment,
  llmModuleKeyFromSegment,
  llmModulePathSegment,
  llmModuleSegment,
} from "./lib/llm-facility-route";
import {
  internalWorkspaceSection,
  isInternalWorkspaceSegment,
  projectPublicKey,
  publicWorkspaceSection,
  resolveProjectPublicKey,
  resolvePublicWorkspaceRoute,
  resolveWorkspaceKey,
  workspaceIdFromPublicSegment,
  workspaceIdsFromKey,
} from "./lib/workspace-route";

type CurrentUserRoutes = {
  active_tenants?: Array<{ tenant_id: string; name: string }>;
  active_projects?: Array<{ tenant_id: string; project_id: string; name: string }>;
};

type ProjectRoute = {
  kind: "project";
  publicKey: string;
  section: string;
};

type WorkspaceKeyRoute = {
  kind: "workspace-key";
  workspaceKey: string;
  section: string;
};

type LegacyWorkspaceRoute = {
  kind: "legacy";
  tenantSegment: string;
  projectSegment: string;
  section: string;
  internal: boolean;
};

type WorkspaceTarget = {
  internalSection: string;
  search: URLSearchParams;
};

const DEFAULT_API_BASE_URL = "http://127.0.0.1:3888";
const DEFAULT_DEV_ACTOR_USER_ID = "10000000-0000-0000-0000-000000000001";
const INTERNAL_WORKSPACE_REWRITE_HEADER = "x-mirofish-workspace-rewrite";

export async function middleware(request: NextRequest) {
  const route = workspaceRouteParts(request.nextUrl.pathname);
  if (!route) {
    return NextResponse.next();
  }
  if (route.kind === "legacy" && route.internal && request.headers.get(INTERNAL_WORKSPACE_REWRITE_HEADER) === "1") {
    return NextResponse.next();
  }

  const sessionCookie = sessionCookieFromHeader(request.headers.get("cookie"));
  if (!sessionCookie && !developmentBypassEnabled()) {
    return loginRedirect(request);
  }

  if (route.kind === "project") {
    const currentUser = await fetchCurrentUserRoutes(sessionCookie);
    const project = currentUser
      ? resolveProjectPublicKey(
          currentUser.active_tenants || [],
          currentUser.active_projects || [],
          route.publicKey,
        )
      : undefined;
    if (!project) {
      return loginRedirect(request);
    }
    const target = resolveWorkspaceTarget(route.section, request.nextUrl.searchParams);
    const canonicalUrl = canonicalProjectUrl(request.nextUrl, route.publicKey, target);
    if (canonicalUrl.pathname !== request.nextUrl.pathname || canonicalUrl.search !== request.nextUrl.search) {
      return NextResponse.redirect(canonicalUrl);
    }
    return rewriteWorkspace(request, project.tenant_id, project.project_id, target);
  }

  if (route.kind === "workspace-key") {
    const decoded = workspaceIdsFromKey(route.workspaceKey);
    if (decoded) {
      return NextResponse.redirect(canonicalProjectUrl(
        request.nextUrl,
        projectPublicKey(decoded.projectId),
        resolveWorkspaceTarget(route.section, request.nextUrl.searchParams),
      ));
    }
    const currentUser = await fetchCurrentUserRoutes(sessionCookie);
    const project = currentUser
      ? resolveWorkspaceKey(
          currentUser.active_tenants || [],
          currentUser.active_projects || [],
          route.workspaceKey,
        )
      : undefined;
    return project
      ? NextResponse.redirect(canonicalProjectUrl(
          request.nextUrl,
          projectPublicKey(project.project_id),
          resolveWorkspaceTarget(route.section, request.nextUrl.searchParams),
        ))
      : loginRedirect(request);
  }

  const tenantID = route.internal ? route.tenantSegment : workspaceIdFromPublicSegment(route.tenantSegment);
  const projectID = route.internal ? route.projectSegment : workspaceIdFromPublicSegment(route.projectSegment);
  if (tenantID && projectID) {
    return NextResponse.redirect(canonicalProjectUrl(
      request.nextUrl,
      projectPublicKey(projectID),
      resolveWorkspaceTarget(route.section, request.nextUrl.searchParams),
    ));
  }

  const currentUser = await fetchCurrentUserRoutes(sessionCookie);
  if (!currentUser) {
    return loginRedirect(request);
  }
  const project = resolvePublicWorkspaceRoute(
    currentUser.active_tenants || [],
    currentUser.active_projects || [],
    route.tenantSegment,
    route.projectSegment,
  );
  return project
    ? NextResponse.redirect(canonicalProjectUrl(
        request.nextUrl,
        projectPublicKey(project.project_id),
        resolveWorkspaceTarget(route.section, request.nextUrl.searchParams),
      ))
    : loginRedirect(request);
}

function resolveWorkspaceTarget(publicSection: string, inputSearch: URLSearchParams): WorkspaceTarget {
  const parts = publicSection.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
  if (parts[0] === "llm" && parts.length === 2 && parts[1] !== "quotas") {
    const search = canonicalLLMFacilitySearch(inputSearch);
    search.set("module", llmModuleSegment(llmModuleKeyFromPathSegment(parts[1])));
    return { internalSection: "llm-facility", search };
  }
  const internalSection = internalWorkspaceSection(publicSection);
  return {
    internalSection,
    search: canonicalWorkspaceSearch(inputSearch, internalSection),
  };
}

function canonicalProjectUrl(url: URL, publicKey: string, target: WorkspaceTarget) {
  const canonical = new URL(url);
  const search = canonicalWorkspaceSearch(target.search, target.internalSection);
  let publicSection = publicWorkspaceSection(target.internalSection);

  if (target.internalSection === "llm-facility") {
    const moduleSegment = search.get("module") || "";
    const moduleKey = moduleSegment ? llmModuleKeyFromSegment(moduleSegment) : DEFAULT_LLM_MODULE_KEY;
    search.delete("module");
    if (moduleKey !== DEFAULT_LLM_MODULE_KEY) {
      publicSection = `llm/${llmModulePathSegment(moduleKey)}`;
    }
  }

  canonical.pathname = `/p/${publicKey}${publicSection ? `/${publicSection}` : ""}`;
  canonical.search = search.toString();
  return canonical;
}

function canonicalWorkspaceSearch(search: URLSearchParams, internalSection: string) {
  if (internalSection === "llm-facility" || internalSection.startsWith("llm-facility/")) {
    return canonicalLLMFacilitySearch(search);
  }
  const result = new URLSearchParams(search);
  for (const [key, value] of result.entries()) {
    if (!value.trim()) {
      result.delete(key);
    }
  }
  return result;
}

function rewriteWorkspace(
  request: NextRequest,
  tenantID: string,
  projectID: string,
  target: WorkspaceTarget,
) {
  const internalUrl = request.nextUrl.clone();
  internalUrl.pathname = `/${tenantID}/projects/${projectID}/${target.internalSection}`;
  internalUrl.search = target.search.toString();
  const internalHeaders = new Headers(request.headers);
  internalHeaders.set(INTERNAL_WORKSPACE_REWRITE_HEADER, "1");
  return NextResponse.rewrite(internalUrl, {
    request: { headers: internalHeaders },
  });
}

export const config = {
  matcher: ["/p/:path*", "/w/:path*", "/:tenantSegment/projects/:projectSegment/:path*"],
};

function workspaceRouteParts(pathname: string): ProjectRoute | WorkspaceKeyRoute | LegacyWorkspaceRoute | undefined {
  const projectMatch = pathname.match(/^\/p\/([^/]+)(?:\/(.*))?$/);
  if (projectMatch) {
    return {
      kind: "project",
      publicKey: decodeURIComponent(projectMatch[1]),
      section: projectMatch[2] || "",
    };
  }

  const workspaceKeyMatch = pathname.match(/^\/w\/([^/]+)(?:\/(.*))?$/);
  if (workspaceKeyMatch) {
    return {
      kind: "workspace-key",
      workspaceKey: decodeURIComponent(workspaceKeyMatch[1]),
      section: workspaceKeyMatch[2] || "",
    };
  }

  const legacyMatch = pathname.match(/^\/([^/]+)\/projects\/([^/]+)(?:\/(.*))?$/);
  if (!legacyMatch) {
    return undefined;
  }
  const tenantSegment = decodeURIComponent(legacyMatch[1]);
  const projectSegment = decodeURIComponent(legacyMatch[2]);
  return {
    kind: "legacy",
    tenantSegment,
    projectSegment,
    section: legacyMatch[3] || "overview",
    internal:
      isInternalWorkspaceSegment(tenantSegment) && isInternalWorkspaceSegment(projectSegment),
  };
}

async function fetchCurrentUserRoutes(sessionCookie: string): Promise<CurrentUserRoutes | undefined> {
  try {
    const headers: Record<string, string> = {};
    if (sessionCookie) {
      headers.cookie = `mirofish_session=${sessionCookie}`;
    } else if (developmentBypassEnabled()) {
      headers["X-User-Id"] = process.env.MIROFISH_WEB_DEV_ACTOR_USER_ID?.trim() || DEFAULT_DEV_ACTOR_USER_ID;
    }
    const response = await fetch(`${process.env.MIROFISH_API_BASE_URL || DEFAULT_API_BASE_URL}/v1/me`, {
      cache: "no-store",
      headers,
    });
    return response.ok ? await response.json() as CurrentUserRoutes : undefined;
  } catch {
    return undefined;
  }
}

function sessionCookieFromHeader(cookieHeader: string | null) {
  if (!cookieHeader) {
    return "";
  }
  for (const part of cookieHeader.split(";")) {
    const [name, ...valueParts] = part.trim().split("=");
    if (name !== "mirofish_session") {
      continue;
    }
    const value = valueParts.join("=").trim();
    if (!value) {
      return "";
    }
    try {
      return decodeURIComponent(value).trim();
    } catch {
      return "";
    }
  }
  return "";
}

function loginRedirect(request: NextRequest) {
  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.search = "";
  return NextResponse.redirect(loginUrl);
}

function developmentBypassEnabled() {
  if (process.env.NODE_ENV === "production") {
    return false;
  }
  return ["1", "true", "on", "yes"].includes(
    process.env.MIROFISH_WEB_DEV_BYPASS_LOGIN?.trim().toLowerCase() || "",
  );
}
