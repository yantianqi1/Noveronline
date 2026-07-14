type TenantRouteRecord = {
  tenant_id: string;
  name: string;
};

type ProjectRouteRecord = {
  tenant_id: string;
  project_id: string;
  name: string;
};

export type WorkspaceRouteProject = ProjectRouteRecord & {
  tenant: TenantRouteRecord;
};

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const BASE64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
const PUBLIC_SECTION_ALIASES: Record<string, string> = {
  overview: "",
  "llm-facility": "llm",
  "character-console": "characters",
  materials: "materials",
  me: "me",
};
const INTERNAL_SECTION_ALIASES = Object.fromEntries(
  Object.entries(PUBLIC_SECTION_ALIASES)
    .filter(([, publicName]) => publicName)
    .map(([internalName, publicName]) => [publicName, internalName]),
);

export function isInternalWorkspaceSegment(value: string) {
  return UUID_PATTERN.test(value);
}

export function workspacePathForProject(
  _tenants: TenantRouteRecord[],
  project: ProjectRouteRecord,
  section = "overview",
) {
  const basePath = workspaceBasePathForProject([], project);
  const publicSection = publicWorkspaceSection(section);
  return publicSection ? `${basePath}/${publicSection}` : basePath;
}

export function workspaceBasePathForProject(
  _tenants: TenantRouteRecord[],
  project: ProjectRouteRecord,
) {
  return `/p/${projectPublicKey(project.project_id)}`;
}

export function projectPublicKey(projectId: string) {
  return opaqueResourceKey(projectId);
}

export function resolveProjectPublicKey(
  tenants: TenantRouteRecord[],
  projects: ProjectRouteRecord[],
  publicKey: string,
): WorkspaceRouteProject | undefined {
  const candidates = projects.filter((project) => projectPublicKey(project.project_id) === publicKey);
  if (candidates.length !== 1) {
    return undefined;
  }
  const project = candidates[0];
  const tenant = tenants.find((item) => item.tenant_id === project.tenant_id);
  return tenant ? { ...project, tenant } : undefined;
}

export function publicWorkspaceSection(section: string) {
  const parts = normalizedSectionParts(section);
  if (parts.length === 0) {
    return "";
  }
  const [first, ...rest] = parts;
  const publicFirst = PUBLIC_SECTION_ALIASES[first] ?? first;
  return [publicFirst, ...rest].filter(Boolean).join("/");
}

export function internalWorkspaceSection(section: string) {
  const parts = normalizedSectionParts(section);
  if (parts.length === 0) {
    return "overview";
  }
  const [first, ...rest] = parts;
  const internalFirst = INTERNAL_SECTION_ALIASES[first] ?? first;
  return [internalFirst, ...rest].join("/");
}

export function matchesWorkspaceNavigationPath(pathname: string, href: string, section: string) {
  if (pathname === href) {
    return true;
  }
  const internalSection = normalizedSectionParts(section).join("/") || "overview";
  if (internalSection !== "overview" && pathname.startsWith(`${href}/`)) {
    return true;
  }
  const internalSuffix = `/${internalSection}`;
  return pathname.endsWith(internalSuffix)
    || (internalSection !== "overview" && pathname.includes(`${internalSuffix}/`));
}

export function workspaceKeyFromIds(tenantId: string, projectId: string) {
  const tenantBytes = uuidBytes(tenantId);
  const projectBytes = uuidBytes(projectId);
  if (tenantBytes && projectBytes) {
    return bytesToBase64Url([...tenantBytes, ...projectBytes]);
  }
  return `x${opaqueResourceKey(tenantId)}${opaqueResourceKey(projectId)}`;
}

export function workspaceIdsFromKey(workspaceKey: string) {
  if (workspaceKey.length !== 43) {
    return undefined;
  }
  const bytes = base64UrlToBytes(workspaceKey);
  if (!bytes || bytes.length !== 32) {
    return undefined;
  }
  return {
    tenantId: uuidFromBytes(bytes.slice(0, 16)),
    projectId: uuidFromBytes(bytes.slice(16)),
  };
}

export function resolveWorkspaceKey(
  tenants: TenantRouteRecord[],
  projects: ProjectRouteRecord[],
  workspaceKey: string,
): WorkspaceRouteProject | undefined {
  const decoded = workspaceIdsFromKey(workspaceKey);
  const candidates = projects.filter((project) => (
    decoded
      ? project.tenant_id === decoded.tenantId && project.project_id === decoded.projectId
      : workspaceKeyFromIds(project.tenant_id, project.project_id) === workspaceKey
  ));
  if (candidates.length !== 1) {
    return undefined;
  }
  const project = candidates[0];
  const tenant = tenants.find((item) => item.tenant_id === project.tenant_id);
  return tenant ? { ...project, tenant } : undefined;
}

export function resolvePublicWorkspaceRoute(
  tenants: TenantRouteRecord[],
  projects: ProjectRouteRecord[],
  tenantSegment: string,
  projectSegment: string,
): WorkspaceRouteProject | undefined {
  const tenantID = workspaceIdFromPublicSegment(tenantSegment);
  const projectID = workspaceIdFromPublicSegment(projectSegment);
  const tenant = tenants.find((item) => segmentMatchesID(tenantSegment, item.tenant_id, tenantID));
  if (!tenant) {
    return undefined;
  }
  const project = projects.find(
    (item) =>
      item.tenant_id === tenant.tenant_id &&
      segmentMatchesID(projectSegment, item.project_id, projectID),
  );
  return project ? { ...project, tenant } : undefined;
}

// Legacy readable segments remain parseable so old bookmarks can redirect once.
export function publicWorkspaceSegment(label: string, id: string) {
  const readable = label
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "workspace";
  return `${readable}-${workspaceSegmentId(id)}`;
}

export function workspaceIdFromPublicSegment(segment: string) {
  const compactID = segment.match(/-([0-9a-f]{32})$/i)?.[1]?.toLocaleLowerCase("en-US");
  if (!compactID) {
    return undefined;
  }
  return [
    compactID.slice(0, 8),
    compactID.slice(8, 12),
    compactID.slice(12, 16),
    compactID.slice(16, 20),
    compactID.slice(20),
  ].join("-");
}

export function opaqueResourceKey(value: string) {
  const first = stableHash(value, 0x811c9dc5);
  const second = stableHash(value, 0x9e3779b9);
  return `${first.toString(36).padStart(7, "0")}${second.toString(36).padStart(7, "0")}`.slice(0, 12);
}

function normalizedSectionParts(section: string) {
  return section.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
}

function uuidBytes(value: string) {
  if (!UUID_PATTERN.test(value)) {
    return undefined;
  }
  const compact = value.replace(/-/g, "");
  return Array.from({ length: 16 }, (_, index) => Number.parseInt(compact.slice(index * 2, index * 2 + 2), 16));
}

function uuidFromBytes(bytes: number[]) {
  const compact = bytes.map((value) => value.toString(16).padStart(2, "0")).join("");
  return [
    compact.slice(0, 8),
    compact.slice(8, 12),
    compact.slice(12, 16),
    compact.slice(16, 20),
    compact.slice(20),
  ].join("-");
}

function bytesToBase64Url(bytes: number[]) {
  let result = "";
  for (let index = 0; index < bytes.length; index += 3) {
    const first = bytes[index];
    const second = bytes[index + 1];
    const third = bytes[index + 2];
    result += BASE64URL_ALPHABET[first >> 2];
    result += BASE64URL_ALPHABET[((first & 3) << 4) | ((second ?? 0) >> 4)];
    if (second !== undefined) {
      result += BASE64URL_ALPHABET[((second & 15) << 2) | ((third ?? 0) >> 6)];
    }
    if (third !== undefined) {
      result += BASE64URL_ALPHABET[third & 63];
    }
  }
  return result;
}

function base64UrlToBytes(value: string) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) {
    return undefined;
  }
  const bytes: number[] = [];
  let bits = 0;
  let bitCount = 0;
  for (const character of value) {
    const decoded = BASE64URL_ALPHABET.indexOf(character);
    if (decoded < 0) {
      return undefined;
    }
    bits = (bits << 6) | decoded;
    bitCount += 6;
    if (bitCount >= 8) {
      bitCount -= 8;
      bytes.push((bits >> bitCount) & 255);
      bits &= (1 << bitCount) - 1;
    }
  }
  return bytes;
}

function stableHash(value: string, seed: number) {
  let hash = seed >>> 0;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash;
}

function workspaceSegmentId(id: string) {
  return id.replace(/-/g, "").toLocaleLowerCase("en-US");
}

function segmentMatchesID(segment: string, id: string, decodedID?: string) {
  if (segment === id || decodedID === id) {
    return true;
  }
  const legacyShortID = segment.split("-").at(-1)?.toLocaleLowerCase("en-US") || "";
  return legacyShortID.length === 8 && workspaceSegmentId(id).startsWith(legacyShortID);
}
