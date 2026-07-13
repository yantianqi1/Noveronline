import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("writer artifact download stays same-origin and forwards HttpOnly session server-side", async () => {
  const route = await fileText("app/api/manuscript-export/[tenantId]/[projectId]/route.ts");
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");
  const client = await fileText("lib/writer-workspace-api.ts");
  const workspace = await fileText("components/writer-product-workspace.tsx");

  assert.match(route, /cookies\(\)/);
  assert.match(route, /get\("mirofish_session"\)/);
  assert.match(route, /searchParams\.get\("exportId"\)/);
  assert.match(route, /\/manuscript\/exports\/\$\{encodeURIComponent\(exportId\)\}\/download/);
  assert.match(route, /createHash\("sha256"\)/);
  assert.match(route, /Content-Disposition/);
  assert.match(route, /X-Content-SHA256/);
  assert.doesNotMatch(route, /X-User-Id|Authorization|api_key|credential_ref/);
  assert.match(page, /createWorkspaceExport/);
  assert.match(client, /manuscript-workspace/);
  assert.match(client, /createWorkspaceExport/);
  assert.match(workspace, /<a className="nav-link" download href=\{`\/api\/manuscript-export\//);
  assert.doesNotMatch(workspace, /<form[^>]+manuscript-export/);
  assert.doesNotMatch(page, /artifact_id:\s*`manuscript-/);
});
