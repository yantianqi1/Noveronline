import assert from "node:assert/strict";
import test from "node:test";

import { disposableLiveDatabaseConfig } from "../scripts/live-test-database.mjs";

test("asset detail browser fixture uses only the isolated live stack", async (t) => {
  const databaseUrl = process.env.MIROFISH_ASSET_DETAIL_BROWSER_LIVE_DATABASE_URL?.trim();
  const appBaseUrl = process.env.MIROFISH_WEB_LIVE_BASE_URL?.trim();
  if (!databaseUrl || !appBaseUrl) {
    t.skip("run through infra/scripts/run-live-test-stack.sh --app");
    return;
  }

  const liveDatabase = await disposableLiveDatabaseConfig(databaseUrl);
  assert.match(liveDatabase.databaseName, /^mirofish_test_/);
  assert.ok(liveDatabase.runtimeUrl, "mirofish.live_test marker was verified");

  const response = await fetch(new URL("/login", appBaseUrl), { redirect: "manual" });
  assert.ok(response.status >= 200 && response.status < 500);
});
