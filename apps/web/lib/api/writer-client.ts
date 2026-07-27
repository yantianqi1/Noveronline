import type {
  BlockListResponse,
  Chapter,
  ChapterListResponse,
  DraftAdoption,
  EventListResponse,
  ManuscriptBlock,
  ManuscriptBlockMeta,
  MessageListResponse,
  WriterDraft,
  WriterEvent,
  WriterMessage,
  WriterRun,
  WriterThread,
} from "@/lib/api/writer-types";

/**
 * Browser-side client for the Writer workbench's canvas + manuscript surface
 * (W1). All calls go to same-origin BFF routes; the browser supplies the
 * tenant via X-Tenant-Id and a CSRF token for mutations. Manuscript mutations
 * also send an `X-Request-Id` (idempotency key) and, for updates, the
 * `expected_version` optimistic lock the Go store requires.
 */

export class WriterError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "WriterError";
  }
}

/** The active project/tenant selection persisted by the shelf. */
export type WriterSelection = { tenant_id: string; project_id: string };

/**
 * Read the active selection, but only if it matches the workbench's project.
 * Returns null when the shelf selection is absent or points at another
 * project, so the workspace can show its "back to the shelf" state.
 */
export function readSelectionFor(projectId: string): WriterSelection | null {
  try {
    const raw = window.sessionStorage.getItem("mirofish.activeProject");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WriterSelection>;
    if (
      typeof parsed.tenant_id === "string" &&
      typeof parsed.project_id === "string" &&
      parsed.project_id === projectId
    ) {
      return { tenant_id: parsed.tenant_id, project_id: parsed.project_id };
    }
    return null;
  } catch {
    return null;
  }
}

async function readError(response: Response): Promise<WriterError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // keep generic message
  }
  return new WriterError(message, code, response.status);
}

/** Idempotency key for manuscript mutations (X-Request-Id). */
function requestId(): string {
  return `writer-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
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
  method: "POST" | "PATCH" | "PUT" | "DELETE",
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
  return (await response.json()) as T;
}

// ── Chapters ─────────────────────────────────────────────────────────────

// Chapters live on the writerworkspace mount, which wraps every response in
// `data` (both the list envelope and single-record mutation results). Blocks
// live on the manuscriptworkspace mount, which returns bare records. Unwrap
// accordingly so callers always get a plain record.
type DataEnvelope<T> = { data: T };

export async function fetchChapters(projectId: string, tenantId: string): Promise<Chapter[]> {
  const data = await getJson<ChapterListResponse>(`/api/projects/${projectId}/chapters`, tenantId);
  const list = data.data ?? [];
  return [...list].sort((a, b) => a.chapter_order - b.chapter_order);
}

export async function createChapter(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  input: { title: string; order: number },
): Promise<Chapter> {
  const envelope = await sendJson<DataEnvelope<Chapter>>(
    "POST",
    `/api/projects/${projectId}/chapters`,
    tenantId,
    csrfToken,
    { title: input.title, order: input.order },
  );
  return envelope.data;
}

export async function renameChapter(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  chapterId: string,
  title: string,
): Promise<Chapter> {
  const envelope = await sendJson<DataEnvelope<Chapter>>(
    "PATCH",
    `/api/projects/${projectId}/chapters/${chapterId}`,
    tenantId,
    csrfToken,
    { title },
  );
  return envelope.data;
}

// ── Manuscript blocks ────────────────────────────────────────────────────

/** List block metadata (no body text), sorted by block_order. */
export async function fetchBlocks(
  projectId: string,
  tenantId: string,
): Promise<ManuscriptBlockMeta[]> {
  const data = await getJson<BlockListResponse>(
    `/api/projects/${projectId}/manuscript-workspace/blocks`,
    tenantId,
  );
  const list = data.blocks ?? [];
  return [...list].sort((a, b) => a.block_order - b.block_order);
}

/** Read a single block with its body text. */
export function fetchBlock(
  projectId: string,
  tenantId: string,
  blockId: string,
): Promise<ManuscriptBlock> {
  return getJson<ManuscriptBlock>(
    `/api/projects/${projectId}/manuscript-workspace/blocks/${blockId}`,
    tenantId,
  );
}

export function createBlock(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  input: { chapter_id?: string; content_text: string },
): Promise<ManuscriptBlock> {
  return sendJson<ManuscriptBlock>(
    "POST",
    `/api/projects/${projectId}/manuscript-workspace/blocks`,
    tenantId,
    csrfToken,
    input,
  );
}

/**
 * Update a block's body text. Requires the current `version` as the
 * optimistic-lock `expected_version`; the store rejects stale writes with a
 * version conflict, which surfaces as a WriterError the canvas can show.
 */
export function updateBlockText(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  blockId: string,
  expectedVersion: number,
  contentText: string,
): Promise<ManuscriptBlock> {
  return sendJson<ManuscriptBlock>(
    "PATCH",
    `/api/projects/${projectId}/manuscript-workspace/blocks/${blockId}`,
    tenantId,
    csrfToken,
    { expected_version: expectedVersion, content_text: contentText },
  );
}

// ── W2: conversation thread ──────────────────────────────────────────────

/** Ensure (get-or-create) the project's conversation thread. */
export async function ensureThread(
  projectId: string,
  tenantId: string,
  csrfToken: string,
): Promise<WriterThread> {
  const envelope = await sendJson<DataEnvelope<WriterThread> | WriterThread>(
    "POST",
    `/api/projects/${projectId}/writer-threads`,
    tenantId,
    csrfToken,
    {},
  );
  return unwrapMaybe(envelope);
}

export async function fetchThreadMessages(
  projectId: string,
  tenantId: string,
  threadId: string,
): Promise<WriterMessage[]> {
  const data = await getJson<MessageListResponse>(
    `/api/projects/${projectId}/writer-threads/${threadId}/messages`,
    tenantId,
  );
  return data.messages ?? [];
}

export async function appendThreadMessage(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  threadId: string,
  input: { role: string; body: string; run_id?: string },
): Promise<WriterMessage> {
  const envelope = await sendJson<DataEnvelope<WriterMessage> | WriterMessage>(
    "POST",
    `/api/projects/${projectId}/writer-threads/${threadId}/messages`,
    tenantId,
    csrfToken,
    input,
  );
  return unwrapMaybe(envelope);
}

// ── W2: writer runs ──────────────────────────────────────────────────────

export function startWriterRun(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  input: { mode: string; instruction: string; chapter_id?: string; scene_id?: string },
): Promise<WriterRun> {
  return sendJson<WriterRun>("POST", `/api/projects/${projectId}/writer-runs`, tenantId, csrfToken, input);
}

export function fetchWriterRun(
  projectId: string,
  tenantId: string,
  runId: string,
): Promise<WriterRun> {
  return getJson<WriterRun>(`/api/projects/${projectId}/writer-runs/${runId}`, tenantId);
}

export function cancelWriterRun(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  runId: string,
): Promise<{ run_id: string; status: string }> {
  return sendJson("POST", `/api/projects/${projectId}/writer-runs/${runId}/cancel`, tenantId, csrfToken);
}

/**
 * Fetch one page of run events. The Go endpoint pages at a fixed 100 events
 * and returns no cursor, so pass `afterEventId` to resume; a page shorter
 * than 100 marks the end.
 */
export async function fetchRunEvents(
  projectId: string,
  tenantId: string,
  runId: string,
  afterEventId?: string,
): Promise<WriterEvent[]> {
  const query = afterEventId ? `?after_event_id=${encodeURIComponent(afterEventId)}` : "";
  const data = await getJson<EventListResponse>(
    `/api/projects/${projectId}/writer-runs/${runId}/events${query}`,
    tenantId,
  );
  return data.items ?? [];
}

// ── W2: candidate adoption ───────────────────────────────────────────────

/**
 * Read a saved candidate draft. With `includeContent` the body text comes
 * along (same block-read permission as manuscript bodies) so a settled rail
 * turn can keep showing the exact prose it drafted. The draft's `status`
 * flips to "adopted" the moment the author adopts it — live turns use this
 * to settle without waiting for their own adopt click to round-trip.
 */
export function fetchWriterDraft(
  projectId: string,
  tenantId: string,
  draftId: string,
  includeContent?: boolean,
): Promise<WriterDraft> {
  const query = includeContent ? "?include=content" : "";
  return getJson<WriterDraft>(`/api/projects/${projectId}/drafts/${draftId}${query}`, tenantId);
}

/**
 * Adopt a candidate draft into the manuscript. Always sends `block_order: 0`
 * so the backend appends at the end (block_order is unique across a project's
 * active blocks; a taken value 503s).
 */
export function adoptDraft(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  draftId: string,
  chapterId?: string,
): Promise<DraftAdoption> {
  return sendJson<DraftAdoption>(
    "POST",
    `/api/projects/${projectId}/drafts/${draftId}/adoptions`,
    tenantId,
    csrfToken,
    { chapter_id: chapterId ?? "", block_order: 0 },
  );
}

/** Unwrap a record that may or may not be `data`-wrapped, depending on mount. */
function unwrapMaybe<T>(value: DataEnvelope<T> | T): T {
  if (value && typeof value === "object" && "data" in (value as DataEnvelope<T>)) {
    const wrapped = (value as DataEnvelope<T>).data;
    if (wrapped !== undefined && wrapped !== null) return wrapped;
  }
  return value as T;
}
