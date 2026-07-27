import {
  missingTenantResponse,
  proxyToApi,
  tenantFrom,
  toResponse,
  upstreamUnavailableResponse,
  UpstreamUnavailableError,
} from "@/lib/server/project-proxy";

const DEFAULT_MAX_SOURCE_UPLOAD_BYTES = 100 * 1024 * 1024;

function sourceUploadMaxBytes(): number {
  const raw = process.env.MIROFISH_SOURCE_UPLOAD_MAX_BYTES?.trim();
  if (!raw) return DEFAULT_MAX_SOURCE_UPLOAD_BYTES;
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error("MIROFISH_SOURCE_UPLOAD_MAX_BYTES must be a positive safe integer");
  }
  return parsed;
}

async function readBodyWithinLimit(request: Request, maxBytes: number): Promise<Uint8Array> {
  const declared = request.headers.get("Content-Length")?.trim();
  if (declared) {
    const parsed = Number(declared);
    if (!Number.isSafeInteger(parsed) || parsed < 0 || parsed > maxBytes) {
      throw new RangeError("SOURCE_FILE_OBJECT_TOO_LARGE");
    }
  }
  if (!request.body) return new Uint8Array();

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) throw new RangeError("SOURCE_FILE_OBJECT_TOO_LARGE");
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

/**
 * BFF proxy → Go `PUT /v1/uploads/{uploadId}/object` (step 2 of upload).
 * Streams the raw file bytes to object storage via the Go API. Content-Type is
 * the source file's MIME type, forwarded so the API can validate it.
 */
export async function PUT(
  request: Request,
  context: { params: Promise<{ uploadId: string }> },
) {
  const { uploadId } = await context.params;
  const tenantId = tenantFrom(request);
  if (!tenantId) {
    return missingTenantResponse();
  }

  let rawBody: Uint8Array;
  try {
    rawBody = await readBodyWithinLimit(request, sourceUploadMaxBytes());
  } catch (error) {
    if (error instanceof RangeError) {
      return Response.json(
        { error: { code: "SOURCE_FILE_OBJECT_TOO_LARGE", message: "上传文件超过大小限制" } },
        { status: 413 },
      );
    }
    return Response.json(
      { error: { code: "UPLOAD_LIMIT_CONFIG_INVALID", message: "上传大小限制配置无效" } },
      { status: 500 },
    );
  }
  const contentType = request.headers.get("Content-Type") ?? "application/octet-stream";

  try {
    const result = await proxyToApi({
      path: `/v1/uploads/${encodeURIComponent(uploadId)}/object`,
      method: "PUT",
      rawBody,
      contentType,
      request,
      tenantId,
    });
    return toResponse(result);
  } catch (error) {
    if (error instanceof UpstreamUnavailableError) {
      return upstreamUnavailableResponse();
    }
    throw error;
  }
}
