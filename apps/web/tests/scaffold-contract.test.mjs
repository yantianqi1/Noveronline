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
  assert.match(login, /LoginForm|LoginPage|登录/);
  assert.match(config, /MIROFISH_API_BASE_URL/);
  assert.match(pkg, /"next"/);
  // Foundation libraries for the rewrite's design system + data layer are
  // expected; the ban below guards against re-importing the retired heavy
  // editor stack, not against building a UI at all.
  assert.match(pkg, /tailwindcss/);
  assert.doesNotMatch(pkg, /@tiptap/);
});
