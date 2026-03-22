import test from "node:test";
import assert from "node:assert/strict";

import config from "../vite.config.js";

test("dev server proxies api requests to backend", () => {
  assert.equal(config.server?.port, 3891);
  assert.equal(config.server?.strictPort, true);
  assert.equal(config.server?.proxy?.["/api"]?.target, "http://127.0.0.1:5101");
});
