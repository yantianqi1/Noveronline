import { randomUUID } from "node:crypto";

export type WriterWebContext = {
  tenantId: string;
  projectId: string;
  actorUserId?: string;
  sessionCookie?: string;
  csrfToken?: string;
};

export type WriterWebFailure = { ok: false; code: string; message: string };
export type WriterWebResult<T> = { ok: true; value: T } | WriterWebFailure;

export type PrivateWritingFields = { brief: string; outline: string; content_text: string };
export type Chapter = {
  chapter_id: string; project_id: string; title: string; status: string; chapter_order: number;
  optimistic_version: number; private?: PrivateWritingFields; created_at: string; updated_at: string;
};
export type Scene = {
  scene_id: string; chapter_id: string; project_id: string; title: string; status: string; scene_order: number;
  optimistic_version: number; private?: PrivateWritingFields; created_at: string; updated_at: string;
};
export type WritingVersion = {
  version_id: string; parent_id: string; title: string; status: string; change_kind: string;
  version_number: number; private?: PrivateWritingFields; created_at: string;
};
export type OutlineVersion = {
  outline_version_id: string; project_id: string; scope_type: string; scope_id?: string; lifecycle: string;
  title: string; outline_text: string; restored_from_version_id?: string; version_number: number; created_at: string;
};
export type BookPlan = {
  book_plan_id: string; project_id: string; title: string; status: string; premise: string; planning: string;
  last_run_id?: string; last_run_status?: string; target_chapter_count?: number; optimistic_version: number;
  created_at: string; updated_at: string;
};
export type WriterPreset = {
  writer_preset_id: string; scope: string; project_id?: string; name: string; description: string;
  settings: string; enabled: boolean; created_at: string; updated_at: string;
};
export type ForbiddenEntry = {
  lexicon_entry_id: string; project_id: string; term: string; category: string; severity: string;
  replacement_guidance: string; enabled: boolean; created_at: string; updated_at: string;
};

export type DraftReviewIssue = {
  issue_id: string; severity: string; category: string; summary: string; suggestion?: string; status: string;
  created_at?: string; updated_at?: string;
};
export type DraftReview = {
  review_id: string; run_id: string; draft_id: string; project_id: string; status: string;
  created_at?: string; updated_at?: string; issues: DraftReviewIssue[];
};
export type DraftReviewList = { draft_id: string; project_id?: string; reviews: DraftReview[] };

export type ManuscriptBlock = {
  block_id: string; project_id: string; chapter_id?: string; scene_id?: string; source_draft_id?: string;
  source_writer_run_id?: string; status: string; tags: string[]; block_order: number; word_count: number;
  version: number; created_at: string; updated_at: string;
};
export type PrivateManuscriptBlock = ManuscriptBlock & { content_text: string };
export type ManuscriptVersion = {
  version_id: string; block_id: string; version_number: number; chapter_id?: string; scene_id?: string;
  status: string; tags: string[]; block_order: number; word_count: number; snapshot_reason: string;
  restored_from_version_id?: string; created_by: string; created_at: string;
};
export type DedupPattern = {
  pattern_id: string; project_id: string; pattern_text: string; normalized_pattern: string; pattern_kind: string;
  lifecycle: string; enabled: boolean; occurrence_count: number; created_at: string; updated_at: string;
};
export type ManuscriptCommand = {
  command_run_id: string; project_id: string; command_type: string; target_chapter_id?: string;
  target_scene_id?: string; target_block_id?: string; starter_kind: string; candidate_kind: string; status: string;
  workflow_run_id?: string; writer_run_id?: string; candidate_count: number; match_count: number; error_code?: string;
  created_at: string; updated_at: string;
};
export type ExportRecord = {
  export_id: string; project_id: string; format: string; status: string; artifact_sha256?: string;
  artifact_size_bytes?: number; block_count: number; error_code?: string; created_at: string;
  completed_at?: string; updated_at: string;
};
export type WriterPlanningAdmission = {
  run_id: string; project_id: string; workflow_type: string; module_key: string; status: string;
  book_plan_id?: string; replay: boolean;
};
export type WriterPlanningRun = {
  run_id: string; workflow_type: string; project_id: string; status: string; progress: number;
  message: string; error_code: string; created_at: string; updated_at: string;
};

const API_BASE_URL = process.env.MIROFISH_API_BASE_URL ?? "http://127.0.0.1:3888";
const projectPath = (context: WriterWebContext, suffix: string) =>
  `/v1/projects/${encodeURIComponent(context.projectId)}${suffix}`;
const manuscriptPath = (context: WriterWebContext, suffix: string) =>
  projectPath(context, `/manuscript-workspace${suffix}`);

export async function listChapters(context: WriterWebContext) { return requestEnvelopeList<Chapter>(context, projectPath(context, "/chapters")); }
export function createChapter(context: WriterWebContext, input: Record<string, unknown>) { return requestEnvelope<Chapter>(context, projectPath(context, "/chapters"), json("POST", input)); }
export function updateChapter(context: WriterWebContext, id: string, input: Record<string, unknown>) { return requestEnvelope<Chapter>(context, `/v1/chapters/${encodeURIComponent(id)}`, json("PATCH", input)); }
export function deleteChapter(context: WriterWebContext, id: string, version: number) { return requestEnvelope<null>(context, `/v1/chapters/${encodeURIComponent(id)}?expected_version=${version}`, { method: "DELETE" }); }
export function reorderChapters(context: WriterWebContext, ids: string[]) { return requestEnvelope<null>(context, projectPath(context, "/chapters/reorder"), json("POST", { ordered_ids: ids })); }
export function listChapterVersions(context: WriterWebContext, id: string) { return requestEnvelopeList<WritingVersion>(context, `/v1/chapters/${encodeURIComponent(id)}/versions?include_private=true`); }
export async function listScenes(context: WriterWebContext, chapterId: string) { return chapterId ? requestEnvelopeList<Scene>(context, `/v1/chapters/${encodeURIComponent(chapterId)}/scenes`) : success([]); }
export function createScene(context: WriterWebContext, chapterId: string, input: Record<string, unknown>) { return requestEnvelope<Scene>(context, `/v1/chapters/${encodeURIComponent(chapterId)}/scenes`, json("POST", input)); }
export function updateScene(context: WriterWebContext, id: string, input: Record<string, unknown>) { return requestEnvelope<Scene>(context, `/v1/scenes/${encodeURIComponent(id)}`, json("PATCH", input)); }
export function deleteScene(context: WriterWebContext, id: string, version: number) { return requestEnvelope<null>(context, `/v1/scenes/${encodeURIComponent(id)}?expected_version=${version}`, { method: "DELETE" }); }
export function reorderScenes(context: WriterWebContext, chapterId: string, ids: string[]) { return requestEnvelope<null>(context, `/v1/chapters/${encodeURIComponent(chapterId)}/scenes/reorder`, json("POST", { ordered_ids: ids })); }
export function listSceneVersions(context: WriterWebContext, id: string) { return requestEnvelopeList<WritingVersion>(context, `/v1/scenes/${encodeURIComponent(id)}/versions?include_private=true`); }
export function listOutlines(context: WriterWebContext, scopeType = "", scopeId = "") { const query = new URLSearchParams(); if (scopeType) query.set("scope_type", scopeType); if (scopeId) query.set("scope_id", scopeId); return requestEnvelopeList<OutlineVersion>(context, `${projectPath(context, "/outlines")}?${query}`); }
export function createOutline(context: WriterWebContext, input: Record<string, unknown>) { return requestEnvelope<OutlineVersion>(context, projectPath(context, "/outlines"), json("POST", input)); }
export function restoreOutline(context: WriterWebContext, id: string) { return requestEnvelope<OutlineVersion>(context, `/v1/outline-versions/${encodeURIComponent(id)}/restore`, json("POST", {})); }
export function listBookPlans(context: WriterWebContext) { return requestEnvelopeList<BookPlan>(context, projectPath(context, "/book-plans")); }
export function createBookPlan(context: WriterWebContext, input: Record<string, unknown>) { return requestEnvelope<BookPlan>(context, projectPath(context, "/book-plans"), json("POST", input)); }
export function updateBookPlan(context: WriterWebContext, id: string, input: Record<string, unknown>) { return requestEnvelope<BookPlan>(context, `/v1/book-plans/${encodeURIComponent(id)}`, json("PATCH", input)); }
export function deleteBookPlan(context: WriterWebContext, id: string, version: number) { return requestEnvelope<null>(context, `/v1/book-plans/${encodeURIComponent(id)}?expected_version=${version}`, { method: "DELETE" }); }
export function startBookPlanGeneration(context: WriterWebContext, id: string, expectedVersion: number) { return requestEnvelope<WriterPlanningAdmission>(context, projectPath(context, `/book-plans/${encodeURIComponent(id)}/generations`), json("POST", { expected_version: expectedVersion })); }
export function listPresets(context: WriterWebContext) { return requestEnvelopeList<WriterPreset>(context, projectPath(context, "/writer-presets")); }
export function upsertProjectPreset(context: WriterWebContext, input: Record<string, unknown>) { return requestEnvelope<WriterPreset>(context, projectPath(context, "/writer-presets"), json("POST", input)); }
export function upsertTenantPreset(context: WriterWebContext, input: Record<string, unknown>) { return requestEnvelope<WriterPreset>(context, `/v1/tenants/${encodeURIComponent(context.tenantId)}/writer-presets`, json("POST", input)); }
export function deletePreset(context: WriterWebContext, id: string) { return requestEnvelope<null>(context, `/v1/writer-presets/${encodeURIComponent(id)}`, { method: "DELETE" }); }
export function listLexicon(context: WriterWebContext) { return requestEnvelopeList<ForbiddenEntry>(context, projectPath(context, "/forbidden-lexicon")); }
export function upsertLexicon(context: WriterWebContext, input: Record<string, unknown>) { return requestEnvelope<ForbiddenEntry>(context, projectPath(context, "/forbidden-lexicon"), json("POST", input)); }
export function deleteLexicon(context: WriterWebContext, id: string) { return requestEnvelope<null>(context, `/v1/forbidden-lexicon/${encodeURIComponent(id)}`, { method: "DELETE" }); }

export async function listDraftReviews(context: WriterWebContext, draftId: string) {
  if (!draftId) return success<DraftReviewList>({ draft_id: "", reviews: [] });
  const result = await requestDirect<DraftReviewList>(context, `/v1/drafts/${encodeURIComponent(draftId)}/reviews`);
  return result.ok ? success({
    ...result.value,
    reviews: asArray(result.value.reviews).map((review) => ({ ...review, issues: asArray(review.issues) })),
  }) : result;
}
export function startDraftReview(context: WriterWebContext, draftId: string, input: Record<string, unknown>) { return requestDirect<Record<string, unknown>>(context, `/v1/drafts/${encodeURIComponent(draftId)}/reviews`, json("POST", input)); }
export function updateReviewIssue(context: WriterWebContext, issueId: string, status: string, version: string) { return requestDirect<Record<string, unknown>>(context, `/v1/draft-review-issues/${encodeURIComponent(issueId)}`, json("PATCH", { status, version })); }

export async function listManuscriptBlocks(context: WriterWebContext, includeDeleted = false) { const result = await requestDirect<{ blocks: ManuscriptBlock[] | null }>(context, manuscriptPath(context, `/blocks${includeDeleted ? "?include_deleted=true" : ""}`)); return result.ok ? success(asArray(result.value.blocks)) : result; }
export function getPrivateBlock(context: WriterWebContext, id: string) { return id ? requestDirect<PrivateManuscriptBlock>(context, manuscriptPath(context, `/blocks/${encodeURIComponent(id)}`)) : success<PrivateManuscriptBlock | null>(null); }
export function createManuscriptBlock(context: WriterWebContext, input: { chapter_id?: string; scene_id?: string; content_text?: string; tags?: string[] }) {
  return requestDirect<PrivateManuscriptBlock>(context, manuscriptPath(context, "/blocks"), json("POST", input));
}
export function updateManuscriptBlock(context: WriterWebContext, id: string, input: Record<string, unknown>) { return requestDirect<PrivateManuscriptBlock>(context, manuscriptPath(context, `/blocks/${encodeURIComponent(id)}`), json("PATCH", input)); }
export function deleteManuscriptBlock(context: WriterWebContext, id: string, version: number) { return requestDirect<ManuscriptBlock>(context, manuscriptPath(context, `/blocks/${encodeURIComponent(id)}`), json("DELETE", { expected_version: version })); }
export function tagManuscriptBlock(context: WriterWebContext, id: string, version: number, tags: string[]) { return requestDirect<ManuscriptBlock>(context, manuscriptPath(context, `/blocks/${encodeURIComponent(id)}/tags`), json("PUT", { expected_version: version, tags })); }
export function reorderManuscriptBlocks(context: WriterWebContext, items: Array<{ block_id: string; expected_version: number }>) { return requestDirect<{ blocks: ManuscriptBlock[] }>(context, manuscriptPath(context, "/blocks/reorder"), json("POST", { items })); }
export function moveManuscriptBlock(context: WriterWebContext, id: string, input: Record<string, unknown>) { return requestDirect<{ blocks: ManuscriptBlock[] }>(context, manuscriptPath(context, `/blocks/${encodeURIComponent(id)}/move`), json("POST", input)); }
export async function listManuscriptVersions(context: WriterWebContext, id: string) { if (!id) return success<ManuscriptVersion[]>([]); const result = await requestDirect<{ versions: ManuscriptVersion[] | null }>(context, manuscriptPath(context, `/blocks/${encodeURIComponent(id)}/versions`)); return result.ok ? success(asArray(result.value.versions)) : result; }
export function restoreManuscriptVersion(context: WriterWebContext, blockId: string, versionId: string, expectedVersion: number) { return requestDirect<PrivateManuscriptBlock>(context, manuscriptPath(context, `/blocks/${encodeURIComponent(blockId)}/versions/${encodeURIComponent(versionId)}/restore`), json("POST", { expected_version: expectedVersion })); }
export async function listDedupPatterns(context: WriterWebContext) { const result = await requestDirect<{ patterns: DedupPattern[] | null }>(context, manuscriptPath(context, "/dedup-patterns?lifecycle=candidate")); return result.ok ? success(asArray(result.value.patterns)) : result; }
export function decideDedupPattern(context: WriterWebContext, id: string, decision: "accept" | "reject") { return requestDirect<DedupPattern>(context, manuscriptPath(context, `/dedup-patterns/${encodeURIComponent(id)}/${decision}`), json("POST", {})); }
export function startDedupExtraction(context: WriterWebContext, input: { block_ids: string[]; chapter_id: string }) { return requestDirect<WriterPlanningAdmission>(context, manuscriptPath(context, "/dedup-extractions"), json("POST", input)); }
export function getWriterPlanningRun(context: WriterWebContext, runId: string) { return runId ? requestDirect<WriterPlanningRun>(context, `/v1/workflow-runs/${encodeURIComponent(runId)}`) : success<WriterPlanningRun | null>(null); }
export function startManuscriptCommand(context: WriterWebContext, input: Record<string, unknown>) { return requestDirect<{ run: ManuscriptCommand; replay: boolean }>(context, manuscriptPath(context, "/commands"), json("POST", input)); }
export function getManuscriptCommand(context: WriterWebContext, id: string) { return id ? requestDirect<ManuscriptCommand>(context, manuscriptPath(context, `/commands/${encodeURIComponent(id)}`)) : success<ManuscriptCommand | null>(null); }
export async function listWorkspaceExports(context: WriterWebContext) { const result = await requestDirect<{ exports: ExportRecord[] | null }>(context, manuscriptPath(context, "/exports")); return result.ok ? success(asArray(result.value.exports)) : result; }
export function createWorkspaceExport(context: WriterWebContext, format = "txt") { return requestDirect<{ export: ExportRecord; replay: boolean }>(context, manuscriptPath(context, "/exports"), json("POST", { format })); }

export type DistillationSettings = {
  project_id: string;
  trigger_mode: "off" | "manual" | "after_adoption" | "chapter_complete";
  enabled_asset_types: string[];
  updated_at?: string;
};
export type AssetProposal = {
  candidate_asset_id: string;
  project_id: string;
  request_id: string;
  operation: string;
  review_status: string;
  normalized_identity: string;
  title: string;
  asset_type: string;
  summary?: string;
  target_asset_id?: string;
  expected_target_version?: number;
  evidence_count: number;
  created_at: string;
};
export type DistillationAdmission = {
  run_id: string;
  request_id: string;
  project_id: string;
  workflow_type: string;
  module_key: string;
  status: string;
  trigger_kind: string;
  replay?: boolean;
};

export function getAssetDistillationSettings(context: WriterWebContext) {
  return requestDirect<DistillationSettings>(context, projectPath(context, "/asset-distillation-settings"));
}
export function patchAssetDistillationSettings(context: WriterWebContext, input: Record<string, unknown>) {
  return requestDirect<DistillationSettings>(context, projectPath(context, "/asset-distillation-settings"), json("PATCH", input));
}
export function startManuscriptAssetDistillation(context: WriterWebContext, input: Record<string, unknown>) {
  return requestDirect<DistillationAdmission>(context, projectPath(context, "/manuscript-asset-distillations"), json("POST", input));
}
export async function listAssetProposals(context: WriterWebContext, status = "pending") {
  const result = await requestDirect<{ items: AssetProposal[] | null }>(
    context,
    `${projectPath(context, "/asset-proposals")}?status=${encodeURIComponent(status)}`,
  );
  return result.ok ? success(asArray(result.value.items)) : result;
}
export function decideAssetProposal(
  context: WriterWebContext,
  candidateAssetId: string,
  input: Record<string, unknown>,
) {
  return requestDirect<{ candidate_asset_id: string; review_status: string; accepted_asset_id?: string; replay?: boolean }>(
    context,
    `/v1/asset-proposals/${encodeURIComponent(candidateAssetId)}/decisions`,
    json("POST", input),
  );
}

function json(method: string, input: unknown): RequestInit { return { method, body: JSON.stringify(input) }; }
function success<T>(value: T): WriterWebResult<T> { return { ok: true, value }; }

async function requestEnvelope<T>(context: WriterWebContext, path: string, init: RequestInit = {}): Promise<WriterWebResult<T>> {
  const result = await rawRequest<{ data?: T }>(context, path, init);
  if (!result.ok) return result;
  if (!isRecord(result.value) || !("data" in result.value)) return success(null as T);
  return success(result.value.data as T);
}

async function requestEnvelopeList<T>(context: WriterWebContext, path: string): Promise<WriterWebResult<T[]>> {
  const result = await requestEnvelope<T[] | null>(context, path);
  return result.ok ? success(asArray(result.value)) : result;
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

async function requestDirect<T>(context: WriterWebContext, path: string, init: RequestInit = {}): Promise<WriterWebResult<T>> {
  return rawRequest<T>(context, path, init);
}

async function rawRequest<T>(context: WriterWebContext, path: string, init: RequestInit): Promise<WriterWebResult<T>> {
  try {
    const method = init.method ?? "GET";
    const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers: requestHeaders(context, method), cache: "no-store" });
    if (response.status === 204) return success(null as T);
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) return decodeFailure(payload, response.status);
    if (!isRecord(payload)) return { ok: false, code: "WRITER_WORKSPACE_INVALID_RESPONSE", message: "Writer workspace returned an invalid response" };
    return success(payload as T);
  } catch {
    return { ok: false, code: "WRITER_WORKSPACE_UNAVAILABLE", message: "Writer workspace is unavailable" };
  }
}

function requestHeaders(context: WriterWebContext, method: string) {
  const headers: Record<string, string> = { Accept: "application/json", "X-Tenant-Id": context.tenantId };
  if (isMutationMethod(method)) {
    headers["Content-Type"] = "application/json";
    headers["X-Request-Id"] = randomUUID();
  }
  if (context.sessionCookie) headers.Cookie = `mirofish_session=${context.sessionCookie}`;
  else if (context.actorUserId) headers["X-User-Id"] = context.actorUserId;
  if (isMutationMethod(method) && context.csrfToken) headers["X-CSRF-Token"] = context.csrfToken;
  return headers;
}

function isMutationMethod(method: string) {
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

function decodeFailure(payload: unknown, status: number): WriterWebFailure {
  if (isRecord(payload) && isRecord(payload.error)) {
    return {
      ok: false,
      code: typeof payload.error.code === "string" ? payload.error.code : `HTTP_${status}`,
      message: typeof payload.error.message === "string" ? payload.error.message : "Writer workspace request failed",
    };
  }
  return { ok: false, code: `HTTP_${status}`, message: "Writer workspace request failed" };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
