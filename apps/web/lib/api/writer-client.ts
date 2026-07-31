import type {
  BlockListResponse,
  Chapter,
  ChapterListResponse,
  DedupPattern,
  DraftAdoption,
  DraftReviewIssue,
  EventListResponse,
  ForbiddenEntry,
  ManuscriptBlock,
  ManuscriptBlockMeta,
  ManuscriptExport,
  MessageListResponse,
  ProjectDraftReviewQueue,
  Scene,
  SceneDetail,
  SceneListResponse,
  WriterDraft,
  WriterEvent,
  WriterMessage,
  WriterPreset,
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

/** Persist a new chapter ordering (drag-reorder). */
export function reorderChapters(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  orderedIds: string[],
): Promise<void> {
  return sendJson<void>(
    "POST",
    `/api/projects/${projectId}/chapters/reorder`,
    tenantId,
    csrfToken,
    { ordered_ids: orderedIds },
  );
}

// ── Scenes ───────────────────────────────────────────────────────────────

// Scenes live on the same writerworkspace mount as chapters (data-wrapped).
// List/create/reorder are project-prefixed; a single scene's read/update is a
// top-level resource (`/api/projects/{id}/scenes/{sceneId}` → `/v1/scenes/{id}`).
export async function fetchScenes(
  projectId: string,
  tenantId: string,
  chapterId: string,
): Promise<Scene[]> {
  const data = await getJson<SceneListResponse>(
    `/api/projects/${projectId}/chapters/${chapterId}/scenes`,
    tenantId,
  );
  const list = data.data ?? [];
  return [...list].sort((a, b) => a.scene_order - b.scene_order);
}

/** Read one scene with its private planning fields (brief/outline). */
export async function fetchScene(
  projectId: string,
  tenantId: string,
  sceneId: string,
): Promise<SceneDetail> {
  const envelope = await getJson<DataEnvelope<SceneDetail>>(
    `/api/projects/${projectId}/scenes/${sceneId}?include_private=true`,
    tenantId,
  );
  return envelope.data;
}

export async function createScene(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  chapterId: string,
  input: { title: string; order: number },
): Promise<Scene> {
  const envelope = await sendJson<DataEnvelope<Scene>>(
    "POST",
    `/api/projects/${projectId}/chapters/${chapterId}/scenes`,
    tenantId,
    csrfToken,
    { title: input.title, order: input.order },
  );
  return envelope.data;
}

/**
 * Update a scene's planning fields. Sends the current `optimistic_version` as
 * the `expected_version` lock; the Go store rejects a stale write with a
 * version conflict, which surfaces as a WriterError.
 */
export async function updateScene(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  sceneId: string,
  input: { expectedVersion: number; title?: string; brief?: string; outline?: string },
): Promise<Scene> {
  const envelope = await sendJson<DataEnvelope<Scene>>(
    "PATCH",
    `/api/projects/${projectId}/scenes/${sceneId}`,
    tenantId,
    csrfToken,
    {
      expected_version: input.expectedVersion,
      ...(input.title !== undefined ? { title: input.title } : {}),
      ...(input.brief !== undefined ? { brief: input.brief } : {}),
      ...(input.outline !== undefined ? { outline: input.outline } : {}),
    },
  );
  return envelope.data;
}

/** Persist a new scene ordering within a chapter (drag-reorder). */
export function reorderScenes(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  chapterId: string,
  orderedIds: string[],
): Promise<void> {
  return sendJson<void>(
    "POST",
    `/api/projects/${projectId}/chapters/${chapterId}/scenes/reorder`,
    tenantId,
    csrfToken,
    { ordered_ids: orderedIds },
  );
}

/**
 * Delete a scene. The Go store requires the current `optimistic_version` as an
 * `expected_version` query param (it returns 204 with no body). A stale version
 * surfaces as a version-conflict WriterError so the caller can refetch.
 */
export function deleteScene(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  sceneId: string,
  expectedVersion: number,
): Promise<void> {
  return sendJson<void>(
    "DELETE",
    `/api/projects/${projectId}/scenes/${sceneId}?expected_version=${expectedVersion}`,
    tenantId,
    csrfToken,
  );
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
  input: {
    mode: string;
    instruction: string;
    chapter_id?: string;
    scene_id?: string;
    /** Worldline sessions whose adopted canon events form the plot timeline (doc 25). */
    worldline_session_ids?: string[];
    /** Saved worldline paths to deep-read during the run. */
    worldline_path_ids?: string[];
  },
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
    // The Go read side always wraps payloads as {"data": ...}; an empty list
    // arrives as {"data": null}. Unwrap unconditionally — returning the whole
    // envelope when data is null would surface the wrapper object where the
    // caller expects the payload (e.g. a non-array crashing `.map`).
    return (value as DataEnvelope<T>).data;
  }
  return value as T;
}

// ── 审校 Review queue ────────────────────────────────────────────────────────

/**
 * The 审校 queue: every draft in the project with issues in `status` (default
 * open), grouped per draft with chapter + run-instruction context. Project-read
 * scoped; returns no body content.
 */
export async function fetchProjectReviewIssues(
  projectId: string,
  tenantId: string,
  status?: string,
): Promise<ProjectDraftReviewQueue> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const response = await getJson<ProjectDraftReviewQueue | DataEnvelope<ProjectDraftReviewQueue>>(
    `/api/projects/${projectId}/draft-review-issues${query}`,
    tenantId,
  );
  const queue = unwrapMaybe(response);
  return { project_id: queue.project_id, items: queue.items ?? [] };
}

/**
 * Triage one review issue. The optimistic-lock `version` is the issue's
 * `updated_at` timestamp string the queue returned. On version conflict the Go
 * store 409s and the caller should refetch rather than retry blindly.
 */
export function updateReviewIssueStatus(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  issueId: string,
  input: { status: "accepted" | "dismissed" | "resolved"; version: string },
): Promise<DraftReviewIssue> {
  return sendJson<DraftReviewIssue>(
    "PATCH",
    `/api/projects/${projectId}/draft-review-issues/${issueId}`,
    tenantId,
    csrfToken,
    { status: input.status, version: input.version },
  );
}

// ── 工具 Tools ───────────────────────────────────────────────────────────────

// Tools endpoints return different envelopes per mount: manuscript-workspace
// (exports, dedup) returns bare maps keyed by resource (`{exports:[...]}`,
// `{patterns:[...]}`); writerworkspace (presets, lexicon) wraps lists in `data`.

/** 导出手稿: list export jobs, newest first. */
export async function fetchManuscriptExports(
  projectId: string,
  tenantId: string,
): Promise<ManuscriptExport[]> {
  const response = await getJson<{ exports?: ManuscriptExport[] | null }>(
    `/api/projects/${projectId}/manuscript-workspace/exports`,
    tenantId,
  );
  return response.exports ?? [];
}

/** 导出手稿: start a new export job in the given format. */
export async function createManuscriptExport(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  format: string,
): Promise<ManuscriptExport> {
  const response = await sendJson<{ export?: ManuscriptExport }>(
    "POST",
    `/api/projects/${projectId}/manuscript-workspace/exports`,
    tenantId,
    csrfToken,
    { format },
  );
  if (!response.export) throw new WriterError("导出任务创建失败", "MANUSCRIPT_EXPORT_FAILED");
  return response.export;
}

/** 违禁词库: list entries. */
export async function fetchForbiddenEntries(projectId: string, tenantId: string): Promise<ForbiddenEntry[]> {
  const response = await getJson<DataEnvelope<ForbiddenEntry[] | null> | ForbiddenEntry[]>(
    `/api/projects/${projectId}/forbidden-lexicon`,
    tenantId,
  );
  return unwrapMaybe(response) ?? [];
}

/** 违禁词库: add an entry. */
export async function createForbiddenEntry(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  input: { term: string; category?: string; severity?: string; replacement_guidance?: string },
): Promise<ForbiddenEntry> {
  const response = await sendJson<DataEnvelope<ForbiddenEntry> | ForbiddenEntry>(
    "POST",
    `/api/projects/${projectId}/forbidden-lexicon`,
    tenantId,
    csrfToken,
    { ...input, enabled: true },
  );
  return unwrapMaybe(response);
}

/** 违禁词库: toggle an entry on/off (upsert preserves the term). */
export function setForbiddenEntryEnabled(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  entry: ForbiddenEntry,
  enabled: boolean,
): Promise<ForbiddenEntry> {
  return sendJson<DataEnvelope<ForbiddenEntry> | ForbiddenEntry>(
    "PATCH",
    `/api/projects/${projectId}/forbidden-lexicon/${entry.lexicon_entry_id}`,
    tenantId,
    csrfToken,
    {
      term: entry.term,
      category: entry.category ?? "",
      severity: entry.severity ?? "",
      replacement_guidance: entry.replacement_guidance ?? "",
      enabled,
    },
  ).then(unwrapMaybe);
}

/** 违禁词库: remove an entry. */
export function deleteForbiddenEntry(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  entryId: string,
): Promise<void> {
  return sendJson<void>(
    "DELETE",
    `/api/projects/${projectId}/forbidden-lexicon/${entryId}`,
    tenantId,
    csrfToken,
  );
}

/** 写作预设: list presets (project scope). */
export async function fetchWriterPresets(projectId: string, tenantId: string): Promise<WriterPreset[]> {
  const response = await getJson<DataEnvelope<WriterPreset[] | null> | WriterPreset[]>(
    `/api/projects/${projectId}/writer-presets`,
    tenantId,
  );
  return unwrapMaybe(response) ?? [];
}

/** 写作预设: toggle a preset on/off (upsert preserves name + settings). */
export function setWriterPresetEnabled(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  preset: WriterPreset,
  enabled: boolean,
): Promise<WriterPreset> {
  return sendJson<DataEnvelope<WriterPreset> | WriterPreset>(
    "PATCH",
    `/api/projects/${projectId}/writer-presets/${preset.writer_preset_id}`,
    tenantId,
    csrfToken,
    {
      name: preset.name,
      description: preset.description ?? "",
      settings: preset.settings ?? "",
      enabled,
    },
  ).then(unwrapMaybe);
}

/** 重复检测: list dedup candidates in the given lifecycle (default candidate). */
export async function fetchDedupPatterns(
  projectId: string,
  tenantId: string,
  lifecycle?: string,
): Promise<DedupPattern[]> {
  const query = lifecycle ? `?lifecycle=${encodeURIComponent(lifecycle)}` : "";
  const response = await getJson<{ patterns?: DedupPattern[] | null }>(
    `/api/projects/${projectId}/manuscript-workspace/dedup-patterns${query}`,
    tenantId,
  );
  return response.patterns ?? [];
}

/** 重复检测: accept or reject a candidate pattern. */
export function reviewDedupPattern(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  patternId: string,
  decision: "accept" | "reject",
): Promise<void> {
  return sendJson<void>(
    "POST",
    `/api/projects/${projectId}/manuscript-workspace/dedup-patterns/${patternId}/${decision}`,
    tenantId,
    csrfToken,
  );
}
