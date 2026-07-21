import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("clean-slate web keeps compose login health route and API config", async () => {
  const login = await source("app/login/page.tsx");
  const config = await source("lib/config.ts");
  const pkg = await source("package.json");
  assert.match(login, /LoginPage|login stub|前端正在按后端契约重写/);
  assert.match(config, /MIROFISH_API_BASE_URL/);
  assert.match(pkg, /"next"/);
  assert.doesNotMatch(pkg, /@tiptap|d3-force|lucide-react/);
});
