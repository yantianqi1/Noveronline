#!/usr/bin/env node

import { spawnSync } from "node:child_process";

const prefix = "MIROFISH_WEB_WORLDLINE_CHARACTER_";
const hasOptIn = Object.keys(process.env).some((key) => key.startsWith(prefix));
if (!hasOptIn) {
  process.stderr.write(`Worldline/Character live journey is opt-in. Set ${prefix}* configuration.\n`);
  process.exitCode = 2;
} else {
  const result = spawnSync(process.execPath, ["--test", "tests/worldline-character-browser-live.test.mjs"], {
    cwd: new URL("..", import.meta.url),
    env: process.env,
    stdio: "inherit",
  });
  const evidence = process.env[`${prefix}EXTERNAL_PROVIDER`] === "1" ? "external" : "local";
  process.stdout.write(`Worldline/Character provider evidence: ${evidence}; status=${result.status === 0 ? "certified" : "not certified"}.\n`);
  process.exitCode = result.status ?? 1;
}
