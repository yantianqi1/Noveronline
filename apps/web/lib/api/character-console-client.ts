import type {
  CharacterEvent,
  CharacterInteraction,
  CharacterProposal,
  CharacterTurn,
} from "@/lib/api/character-console-types";
import { readSelectionFor } from "@/lib/api/writer-client";

/**
 * Browser-side client for the Character Console (角色控制) workbench — the
 * 第一人称舞台. All calls go to same-origin BFF routes; the browser supplies
 * the tenant via X-Tenant-Id (from the shelf selection) and a CSRF token +
 * X-Request-Id for mutations. Reads need no CSRF token.
 *
 * The Go API mounts interaction-scoped routes at the TOP level
 * (/v1/character-interactions/{id}/...); the BFF translates the project-scoped
 * URL shape the browser uses.
 */

export class CharacterConsoleError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "CharacterConsoleError";
  }
}

/** The active project/tenant selection, but only when it matches this project. */
export function readCharacterConsoleSelection(projectId: string) {
  return readSelectionFor(projectId);
}

async function readError(response: Response): Promise<CharacterConsoleError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // non-JSON body — keep the generic message
  }
  return new CharacterConsoleError(message, code, response.status);
}

/** Idempotency key for mutations (X-Request-Id). */
function requestId(): string {
  return `character-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
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

// ── Interactions ───────────────────────────────────────────────────────────

export async function fetchCharacterInteractions(
  projectId: string,
  tenantId: string,
  status?: string,
): Promise<CharacterInteraction[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const data = await getJson<{ items?: CharacterInteraction[] } | CharacterInteraction[]>(
    `/api/projects/${projectId}/character-interactions${query}`,
    tenantId,
  );
  return unwrapItems(data);
}

export function fetchCharacterInteraction(
  projectId: string,
  tenantId: string,
  interactionId: string,
): Promise<CharacterInteraction> {
  return getJson<CharacterInteraction>(
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}`,
    tenantId,
  );
}

/** Descend into a worldline session as one POV agent at an anchor node. */
export function createCharacterInteraction(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  input: {
    worldline_session_id: string;
    anchor_type: string;
    anchor_id: string;
    pov_agent_id: string;
    mode?: string;
    title?: string;
    summary?: string;
    metadata?: Record<string, unknown>;
  },
): Promise<CharacterInteraction> {
  return sendJson<CharacterInteraction>(
    "POST",
    `/api/projects/${projectId}/character-interactions`,
    tenantId,
    csrfToken,
    input,
  );
}

/** Save / archive / resume an interaction (status lifecycle). */
export function updateCharacterInteractionStatus(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  interactionId: string,
  status: string,
): Promise<CharacterInteraction> {
  return sendJson<CharacterInteraction>(
    "PATCH",
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}`,
    tenantId,
    csrfToken,
    { status },
  );
}

// ── Turns (the scene stream) ───────────────────────────────────────────────

export async function fetchCharacterTurns(
  projectId: string,
  tenantId: string,
  interactionId: string,
): Promise<CharacterTurn[]> {
  const data = await getJson<{ items?: CharacterTurn[] } | CharacterTurn[]>(
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/turns`,
    tenantId,
  );
  return unwrapItems(data);
}

/** Append one of my turns (我说 / 我做 / 我内心 / 我想影响). */
export function appendCharacterTurn(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  interactionId: string,
  input: {
    actor_type?: string;
    actor_id?: string;
    turn_kind: string;
    summary: string;
    action?: Record<string, unknown>;
    world_state_delta?: Record<string, unknown>;
    trace_id?: string;
  },
): Promise<CharacterTurn> {
  return sendJson<CharacterTurn>(
    "POST",
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/turns`,
    tenantId,
    csrfToken,
    input,
  );
}

/** Ask the world for the next reaction (character response / world feedback). */
export function startCharacterDialogue(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  interactionId: string,
  input: Record<string, unknown> = {},
): Promise<CharacterTurn> {
  return sendJson<CharacterTurn>(
    "POST",
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/dialogue`,
    tenantId,
    csrfToken,
    input,
  );
}

// ── Events (SSE / replay) ──────────────────────────────────────────────────

export async function fetchCharacterEvents(
  projectId: string,
  tenantId: string,
  interactionId: string,
  afterEventId?: string,
): Promise<CharacterEvent[]> {
  const query = afterEventId ? `?after_event_id=${encodeURIComponent(afterEventId)}` : "";
  const data = await getJson<{ items?: CharacterEvent[] } | CharacterEvent[]>(
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/events${query}`,
    tenantId,
  );
  return unwrapItems(data);
}

// ── Proposals (候选 → 采纳) ───────────────────────────────────────────────

export async function fetchCharacterProposals(
  projectId: string,
  tenantId: string,
  interactionId: string,
): Promise<CharacterProposal[]> {
  const data = await getJson<{ items?: CharacterProposal[] } | CharacterProposal[]>(
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/proposals`,
    tenantId,
  );
  return unwrapItems(data);
}

/** Adopt a proposal into character memory / relations / world state. */
export function adoptCharacterProposal(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  interactionId: string,
  assetId: string,
  note?: string,
): Promise<CharacterProposal> {
  return sendJson<CharacterProposal>(
    "POST",
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/proposals/${encodeURIComponent(assetId)}/adoptions`,
    tenantId,
    csrfToken,
    { note: note ?? "" },
	);
}

/** Persist a proposal rejection so it does not return after a reload. */
export function rejectCharacterProposal(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  interactionId: string,
  assetId: string,
  note?: string,
): Promise<CharacterProposal> {
  return sendJson<CharacterProposal>(
    "POST",
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/proposals/${encodeURIComponent(assetId)}/rejections`,
    tenantId,
    csrfToken,
    { note: note ?? "" },
  );
}

// ── Handoff to Writer (转写为章节草稿) ─────────────────────────────────────

/**
 * Convert the interaction into a chapter draft, handed off to the Writer.
 * Returns the queued run/draft reference — the UI must show "已排队", never
 * claim the draft already exists.
 */
export function convertInteractionToChapterDraft(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  interactionId: string,
  input: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  return sendJson<Record<string, unknown>>(
    "POST",
    `/api/projects/${projectId}/character-interactions/${encodeURIComponent(interactionId)}/chapter-drafts`,
    tenantId,
    csrfToken,
    input,
  );
}
