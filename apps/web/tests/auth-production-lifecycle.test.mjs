import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("production mode cannot enable the development login bypass", async () => {
  const devAccess = await source("lib/dev-access.ts");
  const compose = await source("../../infra/docker-compose.yml");

  assert.match(devAccess, /if\s*\(process\.env\.NODE_ENV === "production"\)\s*\{\s*return false;/s);
  assert.match(compose, /MIROFISH_WEB_DEV_BYPASS_LOGIN:\s*"0"/);
  assert.doesNotMatch(devAccess, /NODE_ENV !== "production"/);
});

test("browser refresh fails closed without a session cookie", async () => {
  const route = await source("app/api/auth/session/refresh/route.ts");
  const missingCookieBranch = route.slice(
    route.indexOf("if (!sessionCookie)"),
    route.indexOf("const csrfResult"),
  );

  assert.match(route, /if\s*\(!sessionCookie\)\s*\{\s*return sessionRefreshFailure\("UNAUTHENTICATED", ""\);/s);
  assert.doesNotMatch(missingCookieBranch, /status:\s*204/);
});

test("compose recovery gate covers auth, tenant denial and queued workflow recovery", async () => {
  const recovery = await source("../../infra/scripts/run-compose-recovery.sh");

  assert.match(recovery, /openssl rand -hex/);
  assert.match(recovery, /status_is 403/);
  assert.match(recovery, /temporal workflow start/);
  assert.match(recovery, /docker compose[^\n]*restart postgres redis temporal minio/);
  assert.match(recovery, /status_is 401/);
  assert.match(recovery, /password\/change/);
  assert.doesNotMatch(recovery, /mirofish_session=|X-CSRF-Token:\s*\$csrf/);
});
