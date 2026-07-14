import { createHash } from "node:crypto";

import type {
  AnalysisToolRequest,
  PiAnalysisDeps,
  ResolveAnalysisModuleRequest,
  SourceSegmentRecord,
  WorkspaceFileRecord,
  WorkspaceFileWriteInput
} from "../activities/pi-analysis-activities.js";
import { isAllowedAnalysisWorkspacePath } from "../contracts/analysis-run.js";
import { assertAnalysisToolAllowed } from "../tools/analysis-permissions.js";
import { analysisRuntimeContextFromInput } from "../contracts/analysis-run.js";
import type { AnalysisRunInput } from "../contracts/analysis-run.js";
import type {
  ClosableQueryExecutor,
  CredentialDecryptor,
  QueryExecutor
} from "./postgres-pi-writer-deps.js";
import type { ObjectStore } from "./object-store.js";
import {
  composeAnalysisAssetTitle,
  mapAnalysisCandidateToAsset,
  normalizeAnalysisCandidateType,
} from "./analysis-asset-mapping.js";
import { effectiveModelCapabilities } from "../llm/model-capabilities.js";

const ANALYSIS_WORKFLOW_TYPE = "analysis_run";
const MAX_WORKSPACE_TEXT_BYTES = 512 * 1024;
const MAX_SOURCE_CHARS = 1_500_000;
const DEFAULT_SEGMENT_CHARS = 12_000;

export interface PostgresPiAnalysisDepsOptions {
  db: QueryExecutor;
  decryptCredential: CredentialDecryptor;
  objectStore?: ObjectStore;
}

export function createPostgresPiAnalysisDeps(options: PostgresPiAnalysisDepsOptions): PiAnalysisDeps {
  const db = options.db;
  return {
    resolveModuleBinding: async (request) => resolveModuleBinding(db, request),
    resolveCredential: async (request) => resolveCredential(options, request),
    writeWorkspaceFile: async (input) => writeWorkspaceFile(db, input),
    listWorkspaceFiles: async (input) => listWorkspaceFiles(db, input),
    listSourceSegments: async (input) => listSourceSegments(db, input),
    readSourceSegment: async (input) => readSourceSegment(db, input),
    executeAnalysisTool: async (request) => executeAnalysisTool(db, request),
    saveAnalysisCandidates: async (input) => saveAnalysisCandidates(db, {
      ...input,
      replace_run: input.replace_run ?? true,
      import_to_assets: input.import_to_assets ?? true
    }),
    preprocessSource: async (input) => preprocessSource(db, input, options.objectStore),
    recordWorkflowEvent: async (request) => recordWorkflowEvent(db, request),
    updateAnalysisRunStatus: async (request) => updateAnalysisRunStatus(db, request),
    findCompletedAnalysisRun: async (request) => findCompletedAnalysisRun(db, request)
  };
}

async function resolveModuleBinding(
  db: QueryExecutor,
  request: ResolveAnalysisModuleRequest
): Promise<{
  module_key: "analysis_planner" | "analysis_worker";
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  credential_ref: string;
  supports_tools: boolean;
  supports_json: boolean;
  settings: Record<string, unknown>;
}> {
  const result = await queryWithTenant(db, request, `
SELECT module_key, channel_id::text AS channel_id, model_id,
       provider, base_url, channel_id::text AS credential_ref,
       supports_tools, supports_json, settings_jsonb
  FROM (
    SELECT b.module_key, b.channel_id, b.model_id,
           c.provider, c.base_url,
           COALESCE(m.supports_tools, false) AS supports_tools,
           COALESCE(m.supports_json, false) AS supports_json,
           b.settings_jsonb,
           CASE WHEN b.project_id = $2 THEN 0 ELSE 1 END AS binding_rank
      FROM llm_module_bindings b
      JOIN llm_channels c
        ON c.channel_id = b.channel_id
       AND c.enabled = TRUE
       AND (c.tenant_id = b.tenant_id OR c.tenant_id IS NULL)
      JOIN llm_models m
        ON m.channel_id = b.channel_id
       AND m.model_id = b.model_id
       AND (m.tenant_id = b.tenant_id OR m.tenant_id IS NULL)
       AND m.enabled = TRUE
     WHERE b.tenant_id = $1
       AND (b.project_id = $2 OR b.project_id IS NULL)
       AND b.module_key = $3
    UNION ALL
    SELECT d.module_key, d.channel_id, d.model_id,
           c.provider, c.base_url,
           COALESCE(m.supports_tools, false) AS supports_tools,
           COALESCE(m.supports_json, false) AS supports_json,
           d.settings_jsonb,
           2 AS binding_rank
      FROM llm_platform_module_defaults d
      JOIN llm_channels c
        ON c.channel_id = d.channel_id
       AND c.enabled = TRUE
       AND c.tenant_id IS NULL
      JOIN llm_models m
        ON m.channel_id = d.channel_id
       AND m.model_id = d.model_id
       AND m.tenant_id IS NULL
       AND m.enabled = TRUE
     WHERE d.module_key = $3
  ) ranked_bindings
 ORDER BY binding_rank
 LIMIT 1`, [request.tenant_id, request.project_id, request.module_key]);
  const row = result.rows[0];
  if (!row) {
    throw Object.assign(new Error(`LLM_MODULE_UNBOUND: ${request.module_key} module is not bound`), {
      code: "LLM_MODULE_UNBOUND"
    });
  }
  return {
    module_key: request.module_key,
    channel_id: String(row.channel_id),
    model_id: String(row.model_id),
    provider: String(row.provider),
    base_url: String(row.base_url),
    credential_ref: String(row.credential_ref),
    supports_tools: row.supports_tools === true,
    supports_json: row.supports_json === true,
    settings: typeof row.settings_jsonb === "object" && row.settings_jsonb
      ? row.settings_jsonb as Record<string, unknown>
      : {}
  };
}

async function resolveCredential(
  options: PostgresPiAnalysisDepsOptions,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    module_key: string;
    channel_id: string;
    credential_ref: string;
  }
): Promise<{ apiKey: string }> {
  const result = await queryWithTenant<{ encrypted_api_key?: string }>(
    options.db,
    request,
    `SELECT encrypted_api_key
       FROM llm_channels
      WHERE channel_id = $1
        AND enabled = TRUE
        AND (tenant_id = $2 OR tenant_id IS NULL)
      ORDER BY tenant_id NULLS LAST
      LIMIT 1`,
    [request.credential_ref, request.tenant_id]
  );
  const encrypted = result.rows[0]?.encrypted_api_key;
  if (typeof encrypted !== "string" || encrypted.trim() === "") {
    throw Object.assign(new Error("LLM_CREDENTIAL_UNAVAILABLE"), { code: "LLM_CREDENTIAL_UNCONFIGURED" });
  }
  return {
    apiKey: await options.decryptCredential(encrypted, {
      tenant_id: request.tenant_id,
      project_id: request.project_id,
      run_id: request.run_id,
      credential_ref: request.credential_ref
    })
  };
}

async function writeWorkspaceFile(
  db: QueryExecutor,
  input: WorkspaceFileWriteInput
): Promise<WorkspaceFileRecord> {
  const path = input.path.trim().replace(/^\/+/, "");
  if (!isAllowedAnalysisWorkspacePath(path)) {
    throw Object.assign(new Error("workspace path is outside the analysis run folder"), {
      code: "TOOL_PERMISSION_DENIED"
    });
  }
  const content = input.content ?? "";
  if (Buffer.byteLength(content, "utf8") > MAX_WORKSPACE_TEXT_BYTES) {
    throw Object.assign(new Error("workspace file exceeds size limit"), {
      code: "VALIDATION_FAILED"
    });
  }
  const sha = createHash("sha256").update(content, "utf8").digest("hex");
  const size = Buffer.byteLength(content, "utf8");
  const objectKey = `projects/${input.project_id}/analysis/${input.run_id}/${path}`;
  const mime = input.mime_type ?? (path.endsWith(".json") ? "application/json" : "text/plain");
  const kind = input.kind || guessKind(path);
  await queryWithTenant(db, input, `
INSERT INTO analysis_workspace_files (
  tenant_id, project_id, run_id, path, kind, mime_type, size_bytes,
  content_sha256, object_key, content_text, updated_at
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10, now()
)
ON CONFLICT (tenant_id, project_id, run_id, path)
DO UPDATE SET
  kind = EXCLUDED.kind,
  mime_type = EXCLUDED.mime_type,
  size_bytes = EXCLUDED.size_bytes,
  content_sha256 = EXCLUDED.content_sha256,
  object_key = EXCLUDED.object_key,
  content_text = EXCLUDED.content_text,
  updated_at = now()`,
  [
    input.tenant_id,
    input.project_id,
    input.run_id,
    path,
    kind,
    mime,
    size,
    sha,
    objectKey,
    content
  ]);
  return {
    path,
    kind,
    size_bytes: size,
    content_sha256: sha,
    content_text: content
  };
}

async function listWorkspaceFiles(
  db: QueryExecutor,
  input: { tenant_id: string; project_id: string; run_id: string }
): Promise<WorkspaceFileRecord[]> {
  const result = await queryWithTenant<{
    path: string;
    kind: string;
    size_bytes: number | string;
    content_sha256: string;
    content_text?: string;
  }>(db, input, `
SELECT path, kind, size_bytes, content_sha256, content_text
  FROM analysis_workspace_files
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND run_id = $3::uuid
 ORDER BY path ASC`, [input.tenant_id, input.project_id, input.run_id]);
  return result.rows.map((row) => ({
    path: row.path,
    kind: row.kind,
    size_bytes: Number(row.size_bytes),
    content_sha256: row.content_sha256,
    content_text: row.content_text
  }));
}

async function listSourceSegments(
  db: QueryExecutor,
  input: { tenant_id: string; project_id: string; source_file_id?: string; limit?: number }
): Promise<SourceSegmentRecord[]> {
  const limit = Math.min(Math.max(input.limit ?? 50, 1), 200);
  const result = await queryWithTenant<{
    segment_order: number | string;
    title_guess?: string;
    preview?: string;
  }>(db, input, `
SELECT segment_order,
       COALESCE(title_guess, chapter_guess, '') AS title_guess,
       left(COALESCE(content_excerpt, summary, ''), 240) AS preview
  FROM text_segments
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND ($3::text = '' OR source_file_id = $3::uuid)
 ORDER BY segment_order ASC
 LIMIT $4`,
  [input.tenant_id, input.project_id, input.source_file_id ?? "", limit]);
  return result.rows.map((row) => ({
    segment_index: Number(row.segment_order),
    title: row.title_guess || undefined,
    char_count: (row.preview ?? "").length,
    preview: row.preview
  }));
}

async function readSourceSegment(
  db: QueryExecutor,
  input: {
    tenant_id: string;
    project_id: string;
    segment_index: number;
    source_file_id?: string;
  }
): Promise<{ segment_index: number; content: string }> {
  const result = await queryWithTenant<{ content_excerpt?: string }>(db, input, `
SELECT COALESCE(content_excerpt, summary, '') AS content_excerpt
  FROM text_segments
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND segment_order = $3
   AND ($4::text = '' OR source_file_id = $4::uuid)
 ORDER BY created_at DESC
 LIMIT 1`,
  [input.tenant_id, input.project_id, input.segment_index, input.source_file_id ?? ""]);
  const content = result.rows[0]?.content_excerpt ?? "";
  return {
    segment_index: input.segment_index,
    content: content.slice(0, 24_000)
  };
}

async function executeAnalysisTool(
  db: QueryExecutor,
  request: AnalysisToolRequest
): Promise<Record<string, unknown>> {
  const context = analysisRuntimeContextFromInput({
    tenant_id: request.tenant_id,
    project_id: request.project_id,
    run_id: request.run_id,
    trace_id: request.run_id,
    requested_by: "",
    mode: "full",
    instruction: "",
    hints: {},
    options: { module_key: "analysis_worker" }
  } satisfies AnalysisRunInput);
  assertAnalysisToolAllowed(request.tool_name, request.args, context);
  switch (request.tool_name) {
    case "list_workspace_files": {
      const files = await listWorkspaceFiles(db, request);
      return {
        file_count: files.length,
        files: files.map((file) => ({
          path: file.path,
          kind: file.kind,
          size_bytes: file.size_bytes,
          content_sha256: file.content_sha256
        }))
      };
    }
    case "read_workspace_file": {
      const path = String(request.args?.path ?? "");
      const files = await listWorkspaceFiles(db, request);
      const file = files.find((item) => item.path === path);
      if (!file) {
        throw Object.assign(new Error("workspace file not found"), { code: "NOT_FOUND" });
      }
      return {
        path: file.path,
        kind: file.kind,
        size_bytes: file.size_bytes,
        content_sha256: file.content_sha256,
        content: (file.content_text ?? "").slice(0, 24_000)
      };
    }
    case "list_source_segments": {
      const segments = await listSourceSegments(db, {
        ...request,
        limit: typeof request.args?.limit === "number" ? request.args.limit : 50
      });
      return { segment_count: segments.length, segments };
    }
    case "read_source_segment": {
      const segmentIndex = Number(request.args?.segment_index ?? 0);
      return readSourceSegment(db, {
        ...request,
        segment_index: segmentIndex
      });
    }
    case "write_workspace_file": {
      const written = await writeWorkspaceFile(db, {
        tenant_id: request.tenant_id,
        project_id: request.project_id,
        run_id: request.run_id,
        path: String(request.args?.path ?? ""),
        kind: String(request.args?.kind ?? "text"),
        content: String(request.args?.content ?? ""),
        mime_type: typeof request.args?.mime_type === "string" ? request.args.mime_type : undefined
      });
      return {
        path: written.path,
        kind: written.kind,
        size_bytes: written.size_bytes,
        content_sha256: written.content_sha256
      };
    }
    case "update_todo": {
      const written = await writeWorkspaceFile(db, {
        tenant_id: request.tenant_id,
        project_id: request.project_id,
        run_id: request.run_id,
        path: "00-plan/todo.json",
        kind: "todo",
        content: JSON.stringify(request.args?.todo ?? request.args ?? {}, null, 2),
        mime_type: "application/json"
      });
      return {
        path: written.path,
        kind: written.kind,
        size_bytes: written.size_bytes,
        content_sha256: written.content_sha256
      };
    }
    case "save_analysis_candidates": {
      const candidates = Array.isArray(request.args?.candidates)
        ? request.args!.candidates as Array<Record<string, unknown>>
        : [];
      return saveAnalysisCandidates(db, {
        tenant_id: request.tenant_id,
        project_id: request.project_id,
        run_id: request.run_id,
        // Mid-run tool saves stay in analysis_candidates only.
        // Finalize replaces the run set and imports into assets once.
        replace_run: false,
        import_to_assets: false,
        candidates: candidates.map((item) => ({
          candidate_type: String(item.candidate_type ?? "note_summary"),
          name: String(item.name ?? ""),
          payload: item,
          workspace_path: typeof item.workspace_path === "string" ? item.workspace_path : undefined
        }))
      });
    }
    default:
      throw Object.assign(new Error(`unknown analysis tool ${request.tool_name}`), {
        code: "TOOL_PERMISSION_DENIED"
      });
  }
}

async function saveAnalysisCandidates(
  db: QueryExecutor,
  input: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    replace_run?: boolean;
    import_to_assets?: boolean;
    candidates: Array<{
      candidate_type: string;
      name: string;
      payload: Record<string, unknown>;
      workspace_path?: string;
    }>;
  }
): Promise<{ candidate_count: number; asset_count?: number }> {
  const importToAssets = input.import_to_assets !== false;
  if (input.replace_run) {
    await queryWithTenant(db, input, `
DELETE FROM analysis_candidates
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND run_id = $3::uuid`,
    [input.tenant_id, input.project_id, input.run_id]);
    // Drop previous auto-imports for this run so finalize is idempotent.
    await queryWithTenant(db, input, `
DELETE FROM assets
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND source_kind = 'pi_analysis'
   AND source_ref LIKE $3 || ':%'`,
    [input.tenant_id, input.project_id, input.run_id]);
  }

  let count = 0;
  let assetCount = 0;
  for (const candidate of input.candidates) {
    const candidateType = normalizeAnalysisCandidateType(candidate.candidate_type);
    const payload = candidate.payload ?? {};
    const title = composeAnalysisAssetTitle(candidateType, candidate.name ?? "", payload);
    const insert = await queryWithTenant<{ candidate_id: string }>(db, input, `
INSERT INTO analysis_candidates (
  tenant_id, project_id, run_id, candidate_type, name, payload_jsonb, status, workspace_path
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, $4, $5, $6::jsonb, $7, $8
)
RETURNING candidate_id::text AS candidate_id`,
    [
      input.tenant_id,
      input.project_id,
      input.run_id,
      candidateType,
      title,
      JSON.stringify(payload),
      importToAssets ? "accepted" : "candidate",
      candidate.workspace_path ?? null
    ]);
    const candidateId = insert.rows[0]?.candidate_id;
    count += 1;
    if (!importToAssets || !candidateId) continue;

    const mapped = mapAnalysisCandidateToAsset(candidateType, title, payload, candidate.workspace_path);
    const sourceRef = `${input.run_id}:${candidateId}`;
    await queryWithTenant(db, input, `
INSERT INTO assets (
  tenant_id, project_id, scope, asset_type, category, lifecycle,
  title, summary, content_text, payload_jsonb, tags_jsonb,
  source_kind, source_ref, enabled, pinned, created_by
) VALUES (
  $1::uuid, $2::uuid, 'project', $3, $4, 'material',
  $5, $6, $7, $8::jsonb, $9::jsonb,
  'pi_analysis', $10, true, false, NULL
)
ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
DO UPDATE SET
  category = EXCLUDED.category,
  lifecycle = 'material',
  summary = EXCLUDED.summary,
  content_text = EXCLUDED.content_text,
  payload_jsonb = EXCLUDED.payload_jsonb,
  tags_jsonb = EXCLUDED.tags_jsonb,
  enabled = true,
  updated_at = now()`,
    [
      input.tenant_id,
      input.project_id,
      mapped.asset_type,
      mapped.category,
      mapped.title,
      mapped.summary,
      mapped.content_text,
      JSON.stringify(mapped.payload),
      JSON.stringify(mapped.tags),
      sourceRef
    ]);
    assetCount += 1;
  }
  return { candidate_count: count, asset_count: assetCount };
}


async function preprocessSource(
  db: QueryExecutor,
  input: AnalysisRunInput & {
    source_object_key?: string;
    source_filename?: string;
    source_mime_type?: string;
    source_size_bytes?: number;
    source_sha256?: string;
  },
  objectStore?: ObjectStore
): Promise<{ segment_count: number }> {
  const maxSegments = Math.min(Math.max(input.options.max_segments ?? 40, 1), 80);
  let segments = await listSourceSegments(db, {
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    source_file_id: input.source_file_id,
    limit: maxSegments
  });

  const hasUsableSegment = segments.some((segment) => {
    const preview = segment.preview ?? "";
    return preview.trim().length > 80 && !preview.includes("Source placeholder");
  });

  if (!hasUsableSegment) {
    const sourceText = await loadSourceText(db, input, objectStore);
    if (!sourceText.trim()) {
      throw Object.assign(new Error("SOURCE_TEXT_UNAVAILABLE: uploaded novel text could not be read"), {
        code: "SOURCE_TEXT_UNAVAILABLE"
      });
    }
    const chunks = splitNovelText(sourceText, DEFAULT_SEGMENT_CHARS, maxSegments);
    for (let index = 0; index < chunks.length; index += 1) {
      const chunk = chunks[index];
      const title = guessSegmentTitle(chunk, index);
      await queryWithTenant(db, input, `
INSERT INTO text_segments (
  tenant_id, project_id, run_id, source_file_id, segment_order,
  title_guess, content_excerpt, summary
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, $4::uuid, $5,
  $6, $7, $8
)
ON CONFLICT (tenant_id, project_id, run_id, segment_order)
DO UPDATE SET
  title_guess = EXCLUDED.title_guess,
  content_excerpt = EXCLUDED.content_excerpt,
  summary = EXCLUDED.summary`,
      [
        input.tenant_id,
        input.project_id,
        input.run_id,
        input.source_file_id ?? null,
        index,
        title,
        chunk.slice(0, 24_000),
        chunk.slice(0, 400)
      ]);
    }
    segments = await listSourceSegments(db, {
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      source_file_id: input.source_file_id,
      limit: maxSegments
    });
  }

  if (segments.length === 0) {
    throw Object.assign(new Error("SOURCE_SEGMENTS_EMPTY: no source segments available for analysis"), {
      code: "SOURCE_SEGMENTS_EMPTY"
    });
  }

  const manifest = {
    source_file_id: input.source_file_id ?? null,
    upload_id: input.upload_id ?? null,
    filename: input.source_filename ?? null,
    mime_type: input.source_mime_type ?? null,
    size_bytes: input.source_size_bytes ?? null,
    sha256: input.source_sha256 ?? null,
    segment_count: segments.length,
    segments: segments.map((segment) => ({
      segment_index: segment.segment_index,
      title: segment.title,
      char_count: segment.char_count
    }))
  };
  await writeWorkspaceFile(db, {
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    path: "10-source/manifest.json",
    kind: "source_manifest",
    content: JSON.stringify(manifest, null, 2),
    mime_type: "application/json"
  });
  for (const segment of segments.slice(0, Math.min(segments.length, 20))) {
    const body = await readSourceSegment(db, {
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      segment_index: segment.segment_index,
      source_file_id: input.source_file_id
    });
    await writeWorkspaceFile(db, {
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      path: `10-source/segments/${segment.segment_index}.txt`,
      kind: "source_segment",
      content: body.content,
      mime_type: "text/plain"
    });
  }
  return { segment_count: segments.length };
}

async function loadSourceText(
  db: QueryExecutor,
  input: AnalysisRunInput & {
    source_object_key?: string;
    source_filename?: string;
    source_mime_type?: string;
  },
  objectStore?: ObjectStore
): Promise<string> {
  let objectKey = input.source_object_key?.trim() ?? "";
  let mimeType = input.source_mime_type?.trim() ?? "";
  if ((!objectKey || !mimeType) && (input.source_file_id || input.upload_id)) {
    const result = await queryWithTenant<{ object_key?: string; mime_type?: string; filename?: string }>(db, input, `
SELECT object_key, mime_type, filename
  FROM source_files
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND (
     ($3::uuid IS NOT NULL AND file_id = $3::uuid)
     OR ($4::uuid IS NOT NULL AND upload_id = $4::uuid)
   )
 ORDER BY created_at DESC
 LIMIT 1`,
    [
      input.tenant_id,
      input.project_id,
      input.source_file_id ?? null,
      input.upload_id ?? null
    ]);
    objectKey = result.rows[0]?.object_key?.trim() ?? objectKey;
    mimeType = result.rows[0]?.mime_type?.trim() ?? mimeType;
    if (!input.source_filename && result.rows[0]?.filename) {
      input.source_filename = result.rows[0].filename;
    }
  }
  if (!objectKey) {
    return "";
  }
  if (!objectStore) {
    throw Object.assign(new Error("OBJECT_STORAGE_UNCONFIGURED: analysis worker cannot read uploaded source files"), {
      code: "OBJECT_STORAGE_UNCONFIGURED"
    });
  }
  const bytes = await objectStore.readBytes(objectKey);
  return decodeSourceBytes(bytes, mimeType, input.source_filename ?? objectKey).slice(0, MAX_SOURCE_CHARS);
}

function decodeSourceBytes(bytes: Buffer, mimeType: string, filename: string): string {
  const lowerMime = mimeType.toLowerCase();
  const lowerName = filename.toLowerCase();
  if (
    lowerMime.includes("pdf")
    || lowerName.endsWith(".pdf")
    || lowerMime.includes("msword")
    || lowerName.endsWith(".docx")
    || lowerName.endsWith(".doc")
  ) {
    throw Object.assign(
      new Error("SOURCE_FORMAT_UNSUPPORTED: analysis currently supports plain text and markdown uploads"),
      { code: "SOURCE_FORMAT_UNSUPPORTED" }
    );
  }
  let text = bytes.toString("utf8");
  if (text.charCodeAt(0) === 0xfeff) {
    text = text.slice(1);
  }
  // Reject obvious binary garbage.
  const sample = text.slice(0, 2000);
  const nulCount = (sample.match(/\u0000/g) ?? []).length;
  if (nulCount > 0) {
    throw Object.assign(new Error("SOURCE_FORMAT_UNSUPPORTED: binary content is not supported"), {
      code: "SOURCE_FORMAT_UNSUPPORTED"
    });
  }
  return text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function splitNovelText(text: string, targetChars: number, maxSegments: number): string[] {
  const normalized = text.trim();
  if (!normalized) return [];
  const chapterPattern = /(?=^(?:第[一二三四五六七八九十百千0-9]+[章节回部卷]|Chapter\s+\d+|CHAPTER\s+\d+)[^\n]{0,40}$)/gmu;
  const roughParts = normalized.split(chapterPattern).map((part) => part.trim()).filter(Boolean);
  const parts = roughParts.length > 1 ? roughParts : [normalized];
  const chunks: string[] = [];
  for (const part of parts) {
    if (part.length <= targetChars) {
      chunks.push(part);
      continue;
    }
    let cursor = 0;
    while (cursor < part.length && chunks.length < maxSegments) {
      let end = Math.min(part.length, cursor + targetChars);
      if (end < part.length) {
        const window = part.slice(cursor, end);
        const breakAt = Math.max(
          window.lastIndexOf("\n\n"),
          window.lastIndexOf("。"),
          window.lastIndexOf("！"),
          window.lastIndexOf("？"),
          window.lastIndexOf("\n")
        );
        if (breakAt > targetChars * 0.4) {
          end = cursor + breakAt + 1;
        }
      }
      const chunk = part.slice(cursor, end).trim();
      if (chunk) chunks.push(chunk);
      cursor = end;
    }
    if (chunks.length >= maxSegments) break;
  }
  return chunks.slice(0, maxSegments);
}

function guessSegmentTitle(chunk: string, index: number): string {
  const firstLine = chunk.split("\n").map((line) => line.trim()).find(Boolean) ?? "";
  if (firstLine.length > 0 && firstLine.length <= 40) {
    return firstLine;
  }
  return `Segment ${index + 1}`;
}

async function recordWorkflowEvent(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    event_type: string;
    payload: Record<string, unknown>;
    idempotency_key?: string;
  }
): Promise<void> {
  const payload = {
    ...sanitizePublicPayload(request.payload),
    ...(request.idempotency_key ? { runtime_event_key: request.idempotency_key } : {})
  };
  await queryWithTenant(db, request, `
WITH locked AS MATERIALIZED (
  SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':' || $2::text || ':analysis-events', 0))
), parent AS (
  SELECT analysis_runs.run_id, analysis_runs.project_id, analysis_runs.workflow_run_id
  FROM analysis_runs
  CROSS JOIN locked
  WHERE analysis_runs.tenant_id = $1::uuid
    AND analysis_runs.project_id = $3::uuid
    AND analysis_runs.run_id = $2::uuid
    AND analysis_runs.status <> 'cancelled'
  LIMIT 1
),
next_sequence AS (
  SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
  FROM workflow_events
  WHERE tenant_id = $1::uuid
    AND run_id = COALESCE((SELECT workflow_run_id FROM parent), $2::uuid)
)
INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT
  $1::uuid,
  COALESCE(parent.workflow_run_id, parent.run_id),
  $4,
  parent.project_id,
  $5,
  next_sequence.sequence,
  $6::jsonb
FROM parent
CROSS JOIN next_sequence
WHERE $7::text IS NULL OR NOT EXISTS (
  SELECT 1 FROM workflow_events existing_event
   WHERE existing_event.tenant_id = $1::uuid
     AND existing_event.run_id = COALESCE(parent.workflow_run_id, parent.run_id)
     AND existing_event.payload_jsonb->>'runtime_event_key' = $7
)`,
  [
    request.tenant_id,
    request.run_id,
    request.project_id,
    ANALYSIS_WORKFLOW_TYPE,
    request.event_type,
    JSON.stringify(payload),
    request.idempotency_key ?? null
  ]);
}

async function updateAnalysisRunStatus(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    status: "running" | "completed" | "failed" | "cancelled";
    error_code?: string;
    error_message?: string;
    result?: Record<string, unknown>;
  }
): Promise<void> {
  await queryWithTenant(db, request, `
WITH analysis_update AS (
  UPDATE analysis_runs
     SET status = $4,
         error_code = $5,
         error_message = $6,
         result_jsonb = CASE WHEN $7::text IS NULL THEN result_jsonb ELSE $7::jsonb END,
         updated_at = now()
   WHERE tenant_id = $1::uuid
     AND project_id = $2::uuid
     AND run_id = $3::uuid
     AND NOT (status = 'cancelled' AND $4 <> 'cancelled')
  RETURNING workflow_run_id
)
UPDATE workflow_runs
   SET status = $4,
       progress = CASE WHEN $4 = 'completed' THEN 100 WHEN $4 = 'failed' THEN 100 WHEN $4 = 'running' THEN 10 ELSE progress END,
       message = $4,
       error_code = $5,
       error_message = $6,
       result_jsonb = CASE WHEN $7::text IS NULL THEN result_jsonb ELSE $7::jsonb END,
       updated_at = now()
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND run_id IN (SELECT workflow_run_id FROM analysis_update WHERE workflow_run_id IS NOT NULL)`,
  [
    request.tenant_id,
    request.project_id,
    request.run_id,
    request.status,
    request.error_code ?? null,
    request.error_message ?? null,
    request.result ? JSON.stringify(request.result) : null
  ]);
}

async function findCompletedAnalysisRun(
  db: QueryExecutor,
  request: { tenant_id: string; project_id: string; run_id: string }
): Promise<{
  tenant_id: string;
  project_id: string;
  run_id: string;
  status: "completed" | "failed";
  candidate_count?: number;
  file_count?: number;
} | null> {
  const result = await queryWithTenant<{
    status: string;
    result_jsonb?: Record<string, unknown>;
  }>(db, request, `
SELECT status, result_jsonb
  FROM analysis_runs
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND run_id = $3::uuid
 LIMIT 1`,
  [request.tenant_id, request.project_id, request.run_id]);
  const row = result.rows[0];
  if (!row || (row.status !== "completed" && row.status !== "failed")) {
    return null;
  }
  const resultJson = row.result_jsonb ?? {};
  return {
    tenant_id: request.tenant_id,
    project_id: request.project_id,
    run_id: request.run_id,
    status: row.status,
    candidate_count: typeof resultJson.candidate_count === "number" ? resultJson.candidate_count : undefined,
    file_count: typeof resultJson.file_count === "number" ? resultJson.file_count : undefined
  };
}

function guessKind(path: string): string {
  if (path.startsWith("00-plan/todo")) return "todo";
  if (path.startsWith("00-plan/hints")) return "hints";
  if (path.startsWith("00-plan/")) return "plan";
  if (path.startsWith("10-source/manifest")) return "source_manifest";
  if (path.startsWith("10-source/")) return "source_segment";
  if (path.startsWith("20-notes/")) return "note";
  if (path.startsWith("30-candidates/")) return "candidate";
  if (path.startsWith("90-review/")) return "review";
  return path.endsWith(".json") ? "json" : "text";
}

function sanitizePublicPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    const lower = key.toLowerCase();
    if (
      lower.includes("api_key")
      || lower.includes("credential")
      || lower.includes("object_key")
      || lower.includes("prompt")
      || lower === "content"
      || lower === "body"
      || lower === "raw"
    ) {
      continue;
    }
    if (typeof value === "string" && value.length > 500) {
      out[key] = `${value.slice(0, 500)}…`;
      continue;
    }
    out[key] = value;
  }
  return out;
}

async function queryWithTenant<T extends Record<string, unknown> = Record<string, unknown>>(
  db: QueryExecutor,
  request: { tenant_id: string; project_id?: string },
  text: string,
  values: readonly unknown[] = []
): Promise<{ rows: T[] }> {
  return db.query<T>(text, values, {
    tenant_id: request.tenant_id,
    project_id: request.project_id
  });
}

export type { ClosableQueryExecutor };
