import {
  apiBaseUrl,
  type ApiFailure,
  type ProjectMembershipSummary,
  type RotatedSessionCookie,
  type TenantMembershipSummary,
} from "./api";

export type RegistrationInput = {
  displayName: string;
  email: string;
  password: string;
  projectTitle: string;
  clientProof?: string;
};

type RegistrationRecord = {
  ok: true;
  user_id: string;
  email: string;
  display_name: string;
  avatar_url: string;
  active_tenants: TenantMembershipSummary[];
  active_projects: ProjectMembershipSummary[];
};

export type RegistrationSummary = (RegistrationRecord & { session_cookie: RotatedSessionCookie }) | ApiFailure;

export async function registerAccount(input: RegistrationInput): Promise<RegistrationSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/auth/signup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(input.clientProof?.trim() ? { "X-Mirofish-Recovery-Client": input.clientProof.trim() } : {}),
      },
      body: JSON.stringify({
        display_name: input.displayName,
        email: input.email,
        password: input.password,
        project_title: input.projectTitle,
      }),
      cache: "no-store",
    });
    const payload = await readPayload(response);
    if (!response.ok) {
      return decodeFailure(payload, response.status);
    }

    const registration = decodeRegistration(payload);
    if (!registration.ok) {
      return registration;
    }
    const sessionCookie = parseSessionCookie(response.headers.get("set-cookie"));
    if (!sessionCookie) {
      return invalidResponse("registration response missing a valid session cookie");
    }
    return {
      ...registration,
      session_cookie: sessionCookie,
    };
  } catch (error) {
    return {
      ok: false,
      code: "REGISTRATION_FAILED",
      message: error instanceof Error ? error.message : "registration request failed",
      request_id: "",
    };
  }
}

function decodeRegistration(payload: Record<string, unknown>): RegistrationRecord | ApiFailure {
  const user = recordFromUnknown(payload.user);
  const activeTenants = decodeTenantMemberships(payload.active_tenants);
  const activeProjects = decodeProjectMemberships(payload.active_projects);
  const userId = stringFromRecord(user, "user_id");
  if (!userId || !activeTenants?.length || !activeProjects?.length) {
    return invalidResponse("registration response missing the personal workspace or first project");
  }
  if (!activeProjects.every((project) => activeTenants.some((workspace) => workspace.tenant_id === project.tenant_id))) {
    return invalidResponse("registration response contains an unowned project");
  }
  return {
    ok: true,
    user_id: userId,
    email: stringFromRecord(user, "email"),
    display_name: stringFromRecord(user, "display_name"),
    avatar_url: stringFromRecord(user, "avatar_url"),
    active_tenants: activeTenants,
    active_projects: activeProjects,
  };
}

function decodeTenantMemberships(value: unknown): TenantMembershipSummary[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const memberships = value.map((item) => {
    const record = recordFromUnknown(item);
    return {
      tenant_id: stringFromRecord(record, "tenant_id"),
      name: stringFromRecord(record, "name"),
      role: stringFromRecord(record, "role"),
      status: stringFromRecord(record, "status"),
    };
  });
  return memberships.every((item) => item.tenant_id && item.name && item.role && item.status) ? memberships : null;
}

function decodeProjectMemberships(value: unknown): ProjectMembershipSummary[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const memberships = value.map((item) => {
    const record = recordFromUnknown(item);
    return {
      tenant_id: stringFromRecord(record, "tenant_id"),
      project_id: stringFromRecord(record, "project_id"),
      name: stringFromRecord(record, "name"),
      role: stringFromRecord(record, "role"),
      status: stringFromRecord(record, "status"),
    };
  });
  return memberships.every((item) => item.tenant_id && item.project_id && item.name && item.role && item.status)
    ? memberships
    : null;
}

function parseSessionCookie(setCookieHeader: string | null): RotatedSessionCookie | null {
  if (!setCookieHeader) {
    return null;
  }
  const cookieHeader = setCookieHeader
    .split(/,(?=\s*[^;,=]+=[^;,]+)/)
    .map((part) => part.trim())
    .find((part) => part.startsWith("mirofish_session="));
  if (!cookieHeader) {
    return null;
  }
  const [nameValue, ...attributes] = cookieHeader.split(";").map((part) => part.trim());
  const value = nameValue.slice("mirofish_session=".length).trim();
  if (!value) {
    return null;
  }

  const cookie: RotatedSessionCookie = {
    value,
    path: "/",
    max_age: 0,
    http_only: false,
    same_site: "lax",
    secure: false,
  };
  for (const attribute of attributes) {
    const [rawName, ...rawValueParts] = attribute.split("=");
    const name = rawName.toLowerCase();
    const rawValue = rawValueParts.join("=").trim();
    if (name === "path" && rawValue) {
      cookie.path = rawValue;
    } else if (name === "max-age") {
      const maxAge = Number.parseInt(rawValue, 10);
      cookie.max_age = Number.isFinite(maxAge) && maxAge > 0 ? maxAge : 0;
    } else if (name === "httponly") {
      cookie.http_only = true;
    } else if (name === "secure") {
      cookie.secure = true;
    } else if (name === "samesite") {
      const sameSite = rawValue.toLowerCase();
      if (sameSite === "lax" || sameSite === "strict" || sameSite === "none") {
        cookie.same_site = sameSite;
      }
    }
  }
  return cookie.http_only && cookie.max_age > 0 ? cookie : null;
}

async function readPayload(response: Response) {
  try {
    const payload = await response.json() as unknown;
    return recordFromUnknown(payload);
  } catch {
    return {};
  }
}

function decodeFailure(payload: Record<string, unknown>, status: number): ApiFailure {
  const error = recordFromUnknown(payload.error);
  return {
    ok: false,
    code: stringFromRecord(error, "code") || "REGISTRATION_FAILED",
    message: stringFromRecord(error, "message") || `HTTP ${status}`,
    request_id: stringFromRecord(error, "request_id"),
  };
}

function invalidResponse(message: string): ApiFailure {
  return {
    ok: false,
    code: "INVALID_API_RESPONSE",
    message,
    request_id: "",
  };
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringFromRecord(record: Record<string, unknown>, key: string) {
  return typeof record[key] === "string" ? record[key] : "";
}
