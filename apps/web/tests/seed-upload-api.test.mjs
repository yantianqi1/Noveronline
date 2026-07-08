import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

afterEach(() => {
  delete process.env.MIROFISH_API_BASE_URL;
  delete globalThis.fetch;
});

test("Seed upload API client preserves admitted source mime through object PUT and Seed start", async () => {
  process.env.MIROFISH_API_BASE_URL = "http://api.test";
  const api = await import(`../lib/api.ts?seedUploadApi=${Date.now()}`);
  const requests = [];
  const uploadedFile = new Blob(["chapter one"], { type: "application/octet-stream" });

  globalThis.fetch = async (url, init = {}) => {
    requests.push({ url: String(url), init });
    if (String(url).endsWith("/v1/projects/project-1/uploads")) {
      return jsonResponse({
        file_id: "file-1",
        upload_id: "upload-1",
        project_id: "project-1",
        filename: "novel.txt",
        mime_type: "text/plain",
        size_bytes: 11,
        sha256: "abc123",
        purpose: "seed",
        parse_status: "pending",
        created_at: "2026-07-09T00:00:00Z",
      });
    }
    if (String(url).endsWith("/v1/uploads/upload-1/object")) {
      return jsonResponse({
        upload_id: "upload-1",
        status: "stored",
      });
    }
    if (String(url).endsWith("/v1/uploads/upload-1/complete")) {
      return jsonResponse({
        file_id: "file-1",
        upload_id: "upload-1",
        project_id: "project-1",
        filename: "novel.txt",
        mime_type: "text/plain",
        size_bytes: 11,
        sha256: "abc123",
        purpose: "seed",
        parse_status: "uploaded",
        created_at: "2026-07-09T00:00:00Z",
      });
    }
    if (String(url).endsWith("/v1/projects/project-1/seed-runs")) {
      return jsonResponse({
        run_id: "run-1",
        project_id: "project-1",
        workflow_type: "seed_pipeline",
        status: "queued",
      });
    }
    return jsonResponse({ error: { code: "NOT_FOUND", message: "not found", request_id: "req-test" } }, 404);
  };

  const context = {
    tenantId: "tenant-1",
    sessionCookie: "session-token",
    csrfToken: "csrf-token",
  };
  const admitted = await api.createSourceFileUpload({
    ...context,
    projectId: "project-1",
    filename: "novel.txt",
    mimeType: "text/plain",
    sizeBytes: 11,
    sha256: "abc123",
    purpose: "seed",
  });
  assert.equal(admitted.ok, true);

  const stored = await api.uploadSourceFileObject({
    ...context,
    uploadId: admitted.upload_id,
    file: uploadedFile,
    mimeType: admitted.mime_type,
  });
  assert.equal(stored.ok, true);

  const completed = await api.completeSourceFileUpload({
    ...context,
    uploadId: admitted.upload_id,
  });
  assert.equal(completed.ok, true);

  const started = await api.startSeedRun({
    ...context,
    projectId: completed.project_id,
    uploadId: completed.upload_id,
    options: { mode: "full" },
  });
  assert.equal(started.ok, true);

  assert.equal(requests.length, 4);
  assert.deepEqual(
    requests.map((request) => [request.init.method ?? "GET", request.url.replace("http://api.test", "")]),
    [
      ["POST", "/v1/projects/project-1/uploads"],
      ["PUT", "/v1/uploads/upload-1/object"],
      ["POST", "/v1/uploads/upload-1/complete"],
      ["POST", "/v1/projects/project-1/seed-runs"],
    ],
  );

  for (const request of requests) {
    assert.equal(request.init.headers["X-Tenant-Id"], "tenant-1");
    assert.equal(request.init.headers.Cookie, "mirofish_session=session-token");
    assert.equal(request.init.headers["X-CSRF-Token"], "csrf-token");
    assert.equal(request.init.cache, "no-store");
  }

  assert.equal(requests[1].init.headers["Content-Type"], "text/plain");
  assert.equal(requests[1].init.body, uploadedFile);

  const admissionBody = JSON.parse(requests[0].init.body);
  assert.deepEqual(admissionBody, {
    filename: "novel.txt",
    mime_type: "text/plain",
    size_bytes: 11,
    sha256: "abc123",
    purpose: "seed",
  });
  assert.equal("tenant_id" in admissionBody, false);
  assert.equal("project_id" in admissionBody, false);
  const seedBody = JSON.parse(requests[3].init.body);
  assert.deepEqual(seedBody, {
    upload_id: "upload-1",
    options: { mode: "full" },
  });
  assert.equal("tenant_id" in seedBody, false);
  assert.equal("project_id" in seedBody, false);

  const serializedRequests = JSON.stringify(requests, (_key, value) => {
    if (value instanceof Blob) {
      return "[blob]";
    }
    return value;
  });
  assert.doesNotMatch(serializedRequests, /tenant_id|project_id.*body|prompt|provider_response|raw_body|content_text|api_key|encrypted_api_key|credential_ref|object_key|draft|manuscript/i);
});

test("Overview upload action passes the sanitized admission mime into object upload", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx");
  const start = page.indexOf("const uploaded = await uploadSourceFileObject({");
  const end = page.indexOf("});", start);
  assert.notEqual(start, -1, "missing uploadSourceFileObject call");
  assert.notEqual(end, -1, "missing uploadSourceFileObject call end");
  const uploadCall = page.slice(start, end);

  assert.match(uploadCall, /uploadId:\s*admitted\.upload_id/);
  assert.match(uploadCall, /file,/);
  assert.match(uploadCall, /mimeType,/);
  assert.doesNotMatch(uploadCall, /application\/octet-stream|api_key|credential_ref|object_key|draft|manuscript|prompt|provider_response/i);
});

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}
