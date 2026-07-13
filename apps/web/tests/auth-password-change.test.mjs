import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("password change client forwards only cookie CSRF and exact password JSON", async () => {
  const client = await fileText("lib/api.ts");
  const start = client.indexOf("export async function changePassword");
  const end = client.indexOf("export async function rotateCurrentSession", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const source = client.slice(start, end);

  assert.match(source, /\/v1\/auth\/password\/change/);
  assert.match(source, /method:\s*"POST"/);
  assert.match(source, /\.\.\.sessionCookieHeaders\(input\)/);
  assert.match(source, /current_password:\s*input\.currentPassword/);
  assert.match(source, /new_password:\s*input\.newPassword/);
  assert.doesNotMatch(source, /Authorization|X-User-Id|tenant_id|project_id|confirmPassword/);
});

test("password change server action keeps session and password material server-side", async () => {
  const actions = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/session-actions.ts");
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const nav = await fileText("components/project-nav.tsx");
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/security/page.tsx");

  assert.match(actions, /export async function changePasswordAction/);
  assert.match(actions, /requireActionCSRFToken\(actionSessionCookie\)/);
  assert.match(actions, /await changePassword\([\s\S]*sessionCookie:\s*actionSessionCookie[\s\S]*csrfToken:\s*csrfResult\.csrf_token/);
  assert.match(actions, /actionCookieStore\.delete\("mirofish_session"\)/);
  assert.match(actions, /redirect\("\/login\?password_changed=1"\)/);
  assert.match(layout, /changePasswordHref=\{`\$\{basePath\}\/security`\}/);
  assert.match(nav, /Account security/);
  assert.match(page, /type="password"/);
  assert.match(page, /autoComplete="current-password"/);
  assert.match(page, /autoComplete="new-password"/);
  assert.doesNotMatch(page, /mirofish_session|csrf_token|sessionCookie|X-CSRF-Token/);
});
