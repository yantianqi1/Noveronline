import type {
  WorldlineEvent,
  WorldlinePreparation,
  WorldlinePreparedAgent,
  WorldlineSavedPath,
  WorldlineSession,
  WorldlineSessionRun,
  WorldlineStepRun,
  WorldlineTimelineEvent,
  WorldlineVariable,
} from "@/lib/api/worldline-types";
import { readSelectionFor } from "@/lib/api/writer-client";

/**
 * Browser-side client for the Worldline (世界线) workbench — the 导演监视器.
 * All calls go to same-origin BFF routes; the browser supplies the tenant via
 * X-Tenant-Id (from the shelf selection) and a CSRF token + X-Request-Id for
 * mutations. Reads need no CSRF token.
 *
 * The Go API mounts run-scoped routes (sessions, preparations, events) at the
 * TOP level; the BFF translates the project-scoped URL shape the browser uses.
 */

export class WorldlineError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "WorldlineError";
  }
}

/** The active project/tenant selection, but only when it matches this project. */
export function readWorldlineSelection(projectId: string) {
  return readSelectionFor(projectId);
}

async function readError(response: Response): Promise<WorldlineError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // non-JSON body — keep the generic message
  }
  return new WorldlineError(message, code, response.status);
}

/** Idempotency key for mutations (X-Request-Id). */
function requestId(): string {
  return `worldline-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

async function getJson<T>(path: string, tenantId: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json", "X-Tenant-Id": tenantId },
    cache: "no-store",
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

async function sendJson<T>(
  method: "POST" | "PATCH",
  path: string,
  tenantId: string,
  csrfToken: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
      "X-Request-Id": requestId(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function unwrapItems<T>(data: { items?: T[] } | T[] | null | undefined): T[] {
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

// ── Sessions ───────────────────────────────────────────────────────────────

export async function fetchWorldlineSessions(
  projectId: string,
  tenantId: string,
): Promise<WorldlineSession[]> {
  const data = await getJson<{ items?: WorldlineSession[] } | WorldlineSession[]>(
    `/api/projects/${projectId}/worldline-sessions`,
    tenantId,
  );
  return unwrapItems(data);
}

export function fetchWorldlineSession(
  projectId: string,
  tenantId: string,
  sessionId: string,
): Promise<WorldlineSession> {
  return getJson<WorldlineSession>(
    `/api/projects/${projectId}/worldline-sessions/${encodeURIComponent(sessionId)}`,
    tenantId,
  );
}

/** Start a goal-driven session (prepares the cast via the cast planner). */
export function startWorldlineSession(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  input: { goal: string; anchor_path_id?: string; options?: Record<string, unknown> },
): Promise<WorldlineSessionRun> {
  return sendJson<WorldlineSessionRun>(
    "POST",
    `/api/projects/${projectId}/worldline-sessions`,
    tenantId,
    csrfToken,
    input,
  );
}

// ── Timeline + events ──────────────────────────────────────────────────────

export async function fetchWorldlineTimeline(
  projectId: string,
  tenantId: string,
  sessionId: string,
): Promise<WorldlineTimelineEvent[]> {
  const data = await getJson<{ items?: WorldlineTimelineEvent[] } | WorldlineTimelineEvent[]>(
    `/api/projects/${projectId}/worldline-sessions/${encodeURIComponent(sessionId)}/timeline`,
    tenantId,
  );
  return unwrapItems(data);
}

export async function fetchWorldlineEvents(
  projectId: string,
  tenantId: string,
  sessionId: string,
  status?: string,
): Promise<WorldlineEvent[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const data = await getJson<{ items?: WorldlineEvent[] } | WorldlineEvent[]>(
    `/api/projects/${projectId}/worldline-sessions/${encodeURIComponent(sessionId)}/events${query}`,
    tenantId,
  );
  return unwrapItems(data);
}

/** Advance the world one step (manual) or in director mode. */
export function startWorldlineStep(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  sessionId: string,
  input: { mode?: string; options?: Record<string, unknown> } = {},
): Promise<WorldlineStepRun> {
  return sendJson<WorldlineStepRun>(
    "POST",
    `/api/projects/${projectId}/worldline-sessions/${encodeURIComponent(sessionId)}/steps`,
    tenantId,
    csrfToken,
    input,
  );
}

/** Kick off continuous auto-evolution (SSE progress follows separately). */
export function startWorldlineAutoEvolution(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  sessionId: string,
  input: { max_steps?: number; until?: Record<string, unknown> } = {},
): Promise<WorldlineStepRun> {
  return sendJson<WorldlineStepRun>(
    "POST",
    `/api/projects/${projectId}/worldline-sessions/${encodeURIComponent(sessionId)}/auto-evolutions`,
    tenantId,
    csrfToken,
    input,
  );
}

/** Adopt a candidate event into canon (候选 → 正史). Explicit author action. */
export function adoptWorldlineEvent(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  eventId: string,
  note?: string,
): Promise<WorldlineEvent> {
  return sendJson<WorldlineEvent>(
    "POST",
    `/api/projects/${projectId}/worldline-events/${encodeURIComponent(eventId)}/adoptions`,
    tenantId,
    csrfToken,
    { note: note ?? "" },
  );
}

/** Edit a candidate event's title/summary/kind before adopting. */
export function updateWorldlineEvent(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  eventId: string,
  patch: Partial<{ title: string; summary: string; kind: string }>,
): Promise<WorldlineEvent> {
  return sendJson<WorldlineEvent>(
    "PATCH",
    `/api/projects/${projectId}/worldline-events/${encodeURIComponent(eventId)}`,
    tenantId,
    csrfToken,
    patch,
  );
}

// ── Variables ──────────────────────────────────────────────────────────────

export function injectWorldlineVariable(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  sessionId: string,
  input: { name: string; description?: string; impact_axis?: string; locked?: boolean; source?: string },
): Promise<WorldlineVariable> {
  return sendJson<WorldlineVariable>(
    "POST",
    `/api/projects/${projectId}/worldline-sessions/${encodeURIComponent(sessionId)}/variables`,
    tenantId,
    csrfToken,
    input,
  );
}

// ── Preparations + cast ────────────────────────────────────────────────────

export async function fetchWorldlinePreparations(
  projectId: string,
  tenantId: string,
): Promise<WorldlinePreparation[]> {
  const data = await getJson<{ items?: WorldlinePreparation[] } | WorldlinePreparation[]>(
    `/api/projects/${projectId}/worldlines/preparations`,
    tenantId,
  );
  return unwrapItems(data);
}

export function fetchWorldlinePreparation(
  projectId: string,
  tenantId: string,
  prepareId: string,
): Promise<WorldlinePreparation> {
  return getJson<WorldlinePreparation>(
    `/api/projects/${projectId}/worldline-preparations/${encodeURIComponent(prepareId)}`,
    tenantId,
  );
}

export async function fetchWorldlinePreparedAgents(
  projectId: string,
  tenantId: string,
  prepareId: string,
): Promise<WorldlinePreparedAgent[]> {
  const data = await getJson<{ items?: WorldlinePreparedAgent[] } | WorldlinePreparedAgent[]>(
    `/api/projects/${projectId}/worldline-preparations/${encodeURIComponent(prepareId)}/agents`,
    tenantId,
  );
  return unwrapItems(data);
}

// ── Saved paths ────────────────────────────────────────────────────────────

export async function fetchWorldlineSavedPaths(
  projectId: string,
  tenantId: string,
): Promise<WorldlineSavedPath[]> {
  const data = await getJson<{ items?: WorldlineSavedPath[] } | WorldlineSavedPath[]>(
    `/api/projects/${projectId}/worldline/saved-paths`,
    tenantId,
  );
  return unwrapItems(data);
}

export function createWorldlineSavedPath(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  sessionId: string,
  input: { title: string; summary?: string; selected_event_ids?: string[]; writer_instruction?: string },
): Promise<WorldlineSavedPath> {
  return sendJson<WorldlineSavedPath>(
    "POST",
    `/api/projects/${projectId}/worldline-sessions/${encodeURIComponent(sessionId)}/saved-paths`,
    tenantId,
    csrfToken,
    input,
  );
}
