import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const originalFetch = globalThis.fetch;

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

afterEach(() => {
  delete process.env.MIROFISH_API_BASE_URL;
  globalThis.fetch = originalFetch;
});

test("Seed upload API client preserves admitted source mime through object PUT and Seed start", async () => {
  const { baseUrl, requests, close } = await startSeedUploadServer();
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedUploadApi=${Date.now()}`);
  const uploadedFile = new Blob(["chapter one"], { type: "application/octet-stream" });

  try {
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
  } finally {
    await close();
  }

  assert.equal(requests.length, 4);
  assert.deepEqual(
    requests.map((request) => [request.method, request.path]),
    [
      ["POST", "/v1/projects/project-1/uploads"],
      ["PUT", "/v1/uploads/upload-1/object"],
      ["POST", "/v1/uploads/upload-1/complete"],
      ["POST", "/v1/projects/project-1/seed-runs"],
    ],
  );

  for (const request of requests) {
    assert.equal(request.headers["x-tenant-id"], "tenant-1");
    assert.equal(hasCookieValue(request.headers.cookie, "mirofish_session"), true, "missing session cookie header");
    assert.equal(typeof request.headers["x-csrf-token"], "string", "missing csrf header");
  }

  assert.equal(requests[1].headers["content-type"], "text/plain");
  assert.equal(requests[1].body.length, 11);
  assert.equal(sha256Hex(requests[1].body), sha256Hex("chapter one"));
  assert.equal(requests[1].headers["content-length"], "11");

  const admissionBody = JSON.parse(requests[0].body);
  assert.deepEqual(admissionBody, {
    filename: "novel.txt",
    mime_type: "text/plain",
    size_bytes: 11,
    sha256: "abc123",
    purpose: "seed",
  });
  assert.equal("tenant_id" in admissionBody, false);
  assert.equal("project_id" in admissionBody, false);
  const seedBody = JSON.parse(requests[3].body);
  assert.deepEqual(seedBody, {
    upload_id: "upload-1",
    options: { mode: "full" },
  });
  assert.equal("tenant_id" in seedBody, false);
  assert.equal("project_id" in seedBody, false);

  const serializedRequestSummary = JSON.stringify(requests.map(safeRequestSummary));
  assert.doesNotMatch(serializedRequestSummary, /tenant_id|project_id.*body|prompt|provider_response|raw_body|content_text|api_key|encrypted_api_key|credential_ref|object_key|draft|manuscript/i);
});

test("Cookie-backed session rotation uses Node transport and parses session Set-Cookie among multiple cookies", async () => {
  const requests = [];
  const server = createServer(async (request, response) => {
    const body = await readRequestBody(request);
    requests.push({
      method: request.method ?? "GET",
      path: request.url ?? "",
      headers: request.headers,
      body,
    });
    response.statusCode = 200;
    response.setHeader("Content-Type", "application/json");
    response.setHeader("Set-Cookie", [
      "theme=dark; Path=/; Max-Age=3600",
      "mirofish_session=rotated-token; Path=/; Max-Age=3600; HttpOnly; SameSite=Lax",
    ]);
    response.end(JSON.stringify({ ok: true }));
  });
  const baseUrl = await listen(server);
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedRotationApi=${Date.now()}`);

  try {
    const result = await api.rotateCurrentSession({
      sessionCookie: "old-token",
      csrfToken: "csrf-token",
    });
    assert.equal(result.ok, true);
    assert.equal(result.session_cookie.value, "rotated-token");
    assert.equal(result.session_cookie.http_only, true);
    assert.equal(result.session_cookie.same_site, "lax");
    assert.equal(result.session_cookie.max_age, 3600);
  } finally {
    await closeServer(server);
  }

  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, "POST");
  assert.equal(requests[0].path, "/v1/auth/session/rotation");
  assert.equal(hasCookieValue(requests[0].headers.cookie, "mirofish_session"), true, "missing rotation cookie header");
  assert.equal(typeof requests[0].headers["x-csrf-token"], "string", "missing rotation csrf header");
});

test("Cookie-backed current user request returns sanitized JSON HTTP failures", async () => {
  const server = createServer(async (request, response) => {
    if (request.url === "/v1/me") {
      writeJson(response, { error: { code: "AUTH_LOOKUP_FAILED", message: "auth lookup failed", request_id: "req-json" } }, 503);
      return;
    }
    writeJson(response, { error: { code: "NOT_FOUND", message: "not found", request_id: "req-test" } }, 404);
  });
  const baseUrl = await listen(server);
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedHttpFailureApi=${Date.now()}`);

  try {
    const jsonFailure = await api.getCurrentUser({ sessionCookie: "session-token" });
    assert.equal(jsonFailure.ok, false);
    assert.equal(jsonFailure.code, "AUTH_LOOKUP_FAILED");
    assertNoSensitiveFailureText(jsonFailure);
  } finally {
    await closeServer(server);
  }
});

test("Cookie-backed current user request returns stable non-JSON HTTP failures", async () => {
  const server = createServer(async (_request, response) => {
    response.statusCode = 502;
    response.setHeader("Content-Type", "text/plain");
    response.end("upstream unavailable");
  });
  const baseUrl = await listen(server);
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedNonJsonFailureApi=${Date.now()}`);

  try {
    const result = await api.getCurrentUser({ sessionCookie: "session-token" });
    assert.equal(result.ok, false);
    assert.equal(result.code, "INVALID_API_RESPONSE");
    assertNoSensitiveFailureText(result);
  } finally {
    await closeServer(server);
  }
});

test("Cookie-backed request errors return stable network failures without raw request material", async () => {
  const server = createServer((request, response) => {
    request.socket.destroy();
    response.destroy();
  });
  const baseUrl = await listen(server);
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedRequestErrorApi=${Date.now()}`);

  try {
    const result = await api.getCurrentUser({ sessionCookie: "session-token" });
    assert.equal(result.ok, false);
    assert.equal(result.code, "CURRENT_USER_QUERY_FAILED");
    assertNoSensitiveFailureText(result);
  } finally {
    await closeServer(server);
  }
});

test("Cookie-backed current user request handles an already-aborted signal without hitting the server", async () => {
  let requestCount = 0;
  const server = createServer((_request, response) => {
    requestCount += 1;
    writeJson(response, { user: {}, active_tenants: [], active_projects: [] });
  });
  const baseUrl = await listen(server);
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedAlreadyAbortApi=${Date.now()}`);
  const controller = new AbortController();
  controller.abort();

  try {
    const result = await api.getCurrentUser({ sessionCookie: "session-token", signal: controller.signal });
    assert.equal(result.ok, false);
    assert.equal(result.code, "CURRENT_USER_QUERY_FAILED");
    assert.equal(requestCount, 0);
    assertNoSensitiveFailureText(result);
  } finally {
    await closeServer(server);
  }
});

test("Cookie-backed current user request handles mid-flight aborts without raw request material", async () => {
  let requestCount = 0;
  const server = createServer((_request, response) => {
    requestCount += 1;
    setTimeout(() => {
      if (!response.destroyed) {
        writeJson(response, { user: {}, active_tenants: [], active_projects: [] });
      }
    }, 250);
  });
  const baseUrl = await listen(server);
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedMidAbortApi=${Date.now()}`);
  const controller = new AbortController();
  const resultPromise = api.getCurrentUser({ sessionCookie: "session-token", signal: controller.signal });
  setTimeout(() => controller.abort(), 10);

  try {
    const result = await resultPromise;
    assert.equal(result.ok, false);
    assert.equal(result.code, "CURRENT_USER_QUERY_FAILED");
    assert.equal(requestCount, 1);
    assertNoSensitiveFailureText(result);
  } finally {
    await closeServer(server);
  }
});

test("Cookie-backed current user request handles aborted partial responses without raw response material", async () => {
  const server = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.write("{\"user\"");
    response.destroy();
  });
  const baseUrl = await listen(server);
  process.env.MIROFISH_API_BASE_URL = baseUrl;
  const api = await import(`../lib/api.ts?seedResponseAbortApi=${Date.now()}`);

  try {
    const result = await api.getCurrentUser({ sessionCookie: "session-token" });
    assert.equal(result.ok, false);
    assert.equal(result.code, "CURRENT_USER_QUERY_FAILED");
    assertNoSensitiveFailureText(result);
  } finally {
    await closeServer(server);
  }
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

async function startSeedUploadServer() {
  const requests = [];
  const server = createServer(async (request, response) => {
    const path = request.url ?? "";
    const body = await readRequestBody(request);
    requests.push({
      method: request.method ?? "GET",
      path,
      headers: request.headers,
      body,
    });
    if (path === "/v1/projects/project-1/uploads") {
      writeJson(response, {
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
      return;
    }
    if (path === "/v1/uploads/upload-1/object") {
      writeJson(response, {
        upload_id: "upload-1",
        status: "stored",
      });
      return;
    }
    if (path === "/v1/uploads/upload-1/complete") {
      writeJson(response, {
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
      return;
    }
    if (path === "/v1/projects/project-1/seed-runs") {
      writeJson(response, {
        run_id: "run-1",
        project_id: "project-1",
        workflow_type: "seed_pipeline",
        status: "queued",
      });
      return;
    }
    writeJson(response, { error: { code: "NOT_FOUND", message: "not found", request_id: "req-test" } }, 404);
  });
  const baseUrl = await listen(server);
  return {
    baseUrl,
    requests,
    close: () => closeServer(server),
  };
}

function writeJson(response, payload, status = 200) {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify(payload));
}

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      assert.equal(typeof address, "object");
      resolve(`http://127.0.0.1:${address.port}`);
    });
  });
}

function closeServer(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}

function readRequestBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    });
    request.on("error", reject);
    request.on("end", () => {
      resolve(Buffer.concat(chunks).toString("utf8"));
    });
  });
}

function hasCookieValue(cookieHeader, name) {
  return String(cookieHeader ?? "")
    .split(";")
    .map((part) => part.trim())
    .some((part) => part.startsWith(`${name}=`));
}

function sha256Hex(value) {
  return createHash("sha256").update(value).digest("hex");
}

function safeRequestSummary(request) {
  return {
    method: request.method,
    path: request.path,
    headerNames: Object.keys(request.headers).sort(),
    bodyLength: request.body.length,
    bodySha256: sha256Hex(request.body),
  };
}

function assertNoSensitiveFailureText(value) {
  const serialized = JSON.stringify(value);
  assert.doesNotMatch(
    serialized,
    /session-token|old-token|csrf-token|chapter one|prompt|provider_response|raw_body|content_text|api_key|encrypted_api_key|credential_ref|object_key|draft|manuscript/i,
  );
}
