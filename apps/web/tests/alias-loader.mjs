/**
 * Node ESM loader hooks for the test suite.
 *
 * Tests import the app's real TypeScript modules (e.g. tests/llm.test.mjs →
 * lib/api/llm.ts) so the logic is exercised, not a copy. Those sources use the
 * bundler conventions tsconfig sets up — the `@/*` path alias and extensionless
 * relative imports — which plain node can't resolve on its own. These two hooks
 * bridge exactly that gap and nothing more:
 *
 *   1. `@/x`            → `<repo>/x`            (tsconfig "paths": { "@/*": ["./*"] })
 *   2. extensionless `./x` → try `./x.ts`, `./x.tsx`, then `./x/index.ts`
 *
 * Registered via `node --import ./tests/register-loader.mjs --test` (see the
 * "test" script in package.json).
 */
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const appRoot = path.resolve(fileURLToPath(import.meta.url), "..", "..");

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith("@/")) {
    const target = pathToFileURL(path.join(appRoot, specifier.slice(2))).href;
    return resolveExtensionless(target, context, nextResolve);
  }
  return resolveExtensionless(null, context, nextResolve, specifier);
}

async function resolveExtensionless(rewritten, context, nextResolve, original) {
  try {
    return await nextResolve(rewritten ?? original, context);
  } catch (error) {
    if (error && error.code !== "ERR_MODULE_NOT_FOUND") throw error;
    const base = rewritten ?? pathToFileURL(path.join(appRoot, original ?? "")).href;
    for (const candidate of [`${base}.ts`, `${base}.tsx`, `${base}/index.ts`]) {
      if (fs.existsSync(fileURLToPath(candidate))) {
        return nextResolve(candidate, context);
      }
    }
    throw error;
  }
}
