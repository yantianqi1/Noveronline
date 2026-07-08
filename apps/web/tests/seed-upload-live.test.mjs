import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { createHash, randomUUID } from "node:crypto";
import { afterEach, test } from "node:test";

const liveSeedUploadTest = hasLiveSeedConfig() ? test : test.skip;
const previousApiBaseUrl = process.env.MIROFISH_API_BASE_URL;

afterEach(() => {
  if (previousApiBaseUrl === undefined) {
    delete process.env.MIROFISH_API_BASE_URL;
    return;
  }
  process.env.MIROFISH_API_BASE_URL = previousApiBaseUrl;
});

liveSeedUploadTest("Web Seed upload client can complete object upload and start a live Seed run", async () => {
  const config = liveSeedConfig();
  assertSafeApiBaseUrl(config);
  process.env.MIROFISH_API_BASE_URL = config.apiBaseUrl;
  const api = await import(`../lib/api.ts?seedUploadLive=${Date.now()}`);
  const authContext = await liveAuthContext(api, config);
  await assertDisposableProject(api, config);
  const sourceText = `MiroFish live seed upload ${randomUUID()}`;
  const sourceBytes = Buffer.from(sourceText, "utf8");
  const admittedMime = "text/plain";
  const file = new Blob([sourceBytes], { type: "application/octet-stream" });

  const admitted = await api.createSourceFileUpload({
    ...authContext,
    projectId: config.projectId,
    filename: `live-seed-${randomUUID()}.txt`,
    mimeType: admittedMime,
    sizeBytes: sourceBytes.byteLength,
    sha256: createHash("sha256").update(sourceBytes).digest("hex"),
    purpose: "seed",
  });
  assertNoForbiddenPublicMarkers(admitted, sourceText);
  assert.equal(admitted.ok, true, publicFailure(admitted));
  assert.equal(admitted.project_id, config.projectId);
  assert.equal(admitted.mime_type, admittedMime);

  const stored = await api.uploadSourceFileObject({
    ...authContext,
    uploadId: admitted.upload_id,
    file,
    mimeType: admitted.mime_type,
  });
  assertNoForbiddenPublicMarkers(stored, sourceText);
  assert.equal(stored.ok, true, publicFailure(stored));
  assert.equal(stored.upload_id, admitted.upload_id);
  assert.equal(stored.status, "stored");

  const completed = await api.completeSourceFileUpload({
    ...authContext,
    uploadId: admitted.upload_id,
  });
  assertNoForbiddenPublicMarkers(completed, sourceText);
  assert.equal(completed.ok, true, publicFailure(completed));
  assert.equal(completed.project_id, config.projectId);
  assert.equal(completed.upload_id, admitted.upload_id);
  assert.equal(completed.parse_status, "uploaded");

  const started = await api.startSeedRun({
    ...authContext,
    projectId: config.projectId,
    uploadId: completed.upload_id,
    options: { mode: "full" },
  });
  assertNoForbiddenPublicMarkers(started, sourceText);
  assert.equal(started.ok, true, publicFailure(started));
  assert.equal(started.project_id, config.projectId);
  assert.equal(started.workflow_type, "seed_pipeline");
  assert.match(started.status, /queued|running|completed/);
});

function hasLiveSeedConfig() {
  const config = liveSeedConfig();
  return Boolean(
    config.apiBaseUrl &&
      config.tenantId &&
      config.projectId &&
      config.sessionCookie &&
      config.allowMutation &&
      config.throwawayProject &&
      config.disposableProjectMarker,
  );
}

function liveSeedConfig() {
  // Opt-in only: this writes a source upload and starts a Seed run in a server-confirmed disposable project.
  return {
    apiBaseUrl: env("MIROFISH_WEB_LIVE_SEED_API_BASE_URL"),
    tenantId: env("MIROFISH_WEB_LIVE_SEED_TENANT_ID"),
    projectId: env("MIROFISH_WEB_LIVE_SEED_PROJECT_ID"),
    sessionCookie: env("MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE"),
    allowMutation: env("MIROFISH_WEB_LIVE_SEED_ALLOW_MUTATION") === "1",
    throwawayProject: env("MIROFISH_WEB_LIVE_SEED_THROWAWAY_PROJECT") === "1",
    disposableProjectMarker: env("MIROFISH_WEB_LIVE_SEED_DISPOSABLE_PROJECT_MARKER"),
  };
}

async function liveAuthContext(api, config) {
  const csrf = await api.getSessionCSRFToken({ sessionCookie: config.sessionCookie });
  assert.equal(csrf.ok, true, publicFailure(csrf));
  return {
    tenantId: config.tenantId,
    sessionCookie: config.sessionCookie,
    csrfToken: csrf.csrf_token,
  };
}

function assertSafeApiBaseUrl(config) {
  const parsed = new URL(config.apiBaseUrl);
  const hostname = parsed.hostname.toLowerCase();
  assert.equal(
    hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1" || hostname === "[::1]",
    true,
    "live Seed upload harness only runs against a local API base URL",
  );
}

async function assertDisposableProject(api, config) {
  const currentUser = await api.getCurrentUser({ sessionCookie: config.sessionCookie });
  assertNoForbiddenPublicMarkers(currentUser);
  assert.equal(currentUser.ok, true, publicFailure(currentUser));
  const project = currentUser.active_projects.find(
    (candidate) =>
      candidate.tenant_id === config.tenantId &&
      candidate.project_id === config.projectId &&
      candidate.status === "active",
  );
  assert.ok(project, "live Seed upload harness target project must be active for the session user");
  const marker = config.disposableProjectMarker.toLowerCase();
  const projectIdentity = `${project.project_id} ${project.name}`.toLowerCase();
  assert.equal(
    projectIdentity.includes(marker),
    true,
    "live Seed upload harness target project must contain the disposable project marker",
  );
}

function assertNoForbiddenPublicMarkers(value, sourceText = "") {
  const serialized = JSON.stringify(value);
  const markers = [
    "pro" + "mpt",
    "pro" + "vider",
    "pro" + "vider" + "_" + "response",
    "pro" + "vider" + "Response",
    "ra" + "w",
    "raw" + "_" + "body",
    "raw" + "Body",
    "con" + "tent",
    "content" + "_" + "text",
    "content" + "Text",
    "source" + "_" + "text",
    "source" + "Text",
    "api" + "_" + "key",
    "api" + "Key",
    "encrypted" + "_" + "api" + "_" + "key",
    "encrypted" + "Credential",
    "creden" + "tial",
    "credential" + "_" + "ref",
    "credential" + "Ref",
    "object" + "_" + "key",
    "object" + "Key",
    "dra" + "ft",
    "manu" + "script",
  ];
  if (sourceText) {
    markers.push(sourceText);
  }
  for (const marker of markers) {
    assert.equal(
      serialized.toLowerCase().includes(marker.toLowerCase()),
      false,
      `live response leaked marker ${marker}`,
    );
  }
  assertNoForbiddenPublicKeys(value);
}

function assertNoForbiddenPublicKeys(value, path = "response") {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoForbiddenPublicKeys(item, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  const forbiddenKeys = new Set([
    "raw",
    "content",
    "credential",
    "pro" + "mpt",
    "pro" + "vider",
    "providerresponse",
    "rawbody",
    "contenttext",
    "sourcetext",
    "apikey",
    "encryptedapikey",
    "encryptedcredential",
    "credentialref",
    "objectkey",
    "dra" + "ft",
    "manu" + "script",
  ]);
  for (const [key, item] of Object.entries(value)) {
    const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, "");
    assert.equal(forbiddenKeys.has(normalized), false, `live response leaked public key ${path}.${key}`);
    assertNoForbiddenPublicKeys(item, `${path}.${key}`);
  }
}

function publicFailure(result) {
  if (result?.ok !== false) {
    return "";
  }
  return `${result.code}: ${result.message}`;
}

function env(name) {
  return process.env[name]?.trim() ?? "";
}
