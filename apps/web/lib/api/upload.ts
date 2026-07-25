import type { SourceFile } from "@/lib/api/overview-types";
import { OverviewError } from "@/lib/api/overview-client";

/**
 * Three-step source-file upload orchestration, matching the Go control plane:
 *   1. POST /v1/projects/{id}/uploads     → create the record (metadata+sha256)
 *   2. PUT  /v1/uploads/{uploadId}/object → stream the raw bytes to storage
 *   3. POST /v1/uploads/{uploadId}/complete → finalize the source file
 * Progress is reported as a coarse phase so the UI can show honest stages
 * (client fetch can't stream byte-level progress without extra machinery).
 */

export type UploadPhase = "hashing" | "creating" | "uploading" | "completing" | "done";

export const UPLOAD_PHASE_LABELS: Record<UploadPhase, string> = {
  hashing: "校验文件",
  creating: "登记",
  uploading: "上传",
  completing: "完成",
  done: "已就绪",
};

const SUPPORTED_MIME = new Map<string, string>([
  ["txt", "text/plain"],
  ["md", "text/markdown"],
  ["markdown", "text/markdown"],
  ["pdf", "application/pdf"],
]);

/** Resolve a supported source MIME type from the filename, or null. */
export function supportedSourceMime(filename: string): string | null {
  const ext = filename.split(".").pop()?.toLowerCase().trim() ?? "";
  return SUPPORTED_MIME.get(ext) ?? null;
}

export function isSupportedSourceFile(filename: string): boolean {
  return supportedSourceMime(filename) !== null;
}

async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function readError(response: Response, fallback: string): Promise<OverviewError> {
  let code: string | undefined;
  let message = fallback;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // keep fallback
  }
  return new OverviewError(message, code, response.status);
}

export type UploadResult = {
  sourceFile: SourceFile;
  uploadId: string;
};

export async function uploadSourceFile(options: {
  projectId: string;
  tenantId: string;
  csrfToken: string;
  file: File;
  onPhase?: (phase: UploadPhase) => void;
}): Promise<UploadResult> {
  const { projectId, tenantId, csrfToken, file, onPhase } = options;

  const mimeType = supportedSourceMime(file.name);
  if (!mimeType) {
    throw new OverviewError("仅支持 TXT / MD / PDF 原文文件", "UNSUPPORTED_FILE_TYPE", 400);
  }

  onPhase?.("hashing");
  const buffer = await file.arrayBuffer();
  const sha256 = await sha256Hex(buffer);

  // Step 1: create the upload record.
  onPhase?.("creating");
  const createResponse = await fetch(`/api/projects/${projectId}/uploads`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({
      filename: file.name,
      mime_type: mimeType,
      size_bytes: file.size,
      sha256,
      purpose: "novel_source",
    }),
  });
  if (!createResponse.ok) {
    throw await readError(createResponse, "登记上传失败");
  }
  const created = (await createResponse.json()) as SourceFile;
  const uploadId = created.upload_id;
  if (!uploadId) {
    throw new OverviewError("上传登记未返回 upload_id", "UPLOAD_ID_MISSING", 500);
  }

  // Step 2: PUT the raw bytes.
  onPhase?.("uploading");
  const putResponse = await fetch(`/api/uploads/${uploadId}/object`, {
    method: "PUT",
    headers: {
      "Content-Type": mimeType,
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
    },
    body: buffer,
  });
  if (!putResponse.ok) {
    throw await readError(putResponse, "上传文件内容失败");
  }

  // Step 3: complete the upload.
  onPhase?.("completing");
  const completeResponse = await fetch(`/api/uploads/${uploadId}/complete`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({}),
  });
  if (!completeResponse.ok) {
    throw await readError(completeResponse, "完成上传失败");
  }
  const sourceFile = (await completeResponse.json()) as SourceFile;

  onPhase?.("done");
  return { sourceFile, uploadId };
}

/** Human-readable file size. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}
