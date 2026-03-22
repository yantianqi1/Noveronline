import test from "node:test";
import assert from "node:assert/strict";

import { buildApiUrl, resolveApiBaseUrl } from "../src/api/apiBase.js";

test("defaults to same-origin api base in browser", () => {
  const apiBaseUrl = resolveApiBaseUrl({
    envBaseUrl: "",
    windowObject: {
      location: {
        protocol: "http:",
        hostname: "127.0.0.1",
        port: "3891",
      },
    },
  });

  assert.equal(apiBaseUrl, "");
});

test("prefers explicit api base url from env", () => {
  const apiBaseUrl = resolveApiBaseUrl({
    envBaseUrl: "http://127.0.0.1:5101",
    windowObject: {
      location: {
        protocol: "http:",
        hostname: "127.0.0.1",
        port: "3891",
      },
    },
  });

  assert.equal(apiBaseUrl, "http://127.0.0.1:5101");
});

test("builds relative urls when api base is empty", () => {
  assert.equal(buildApiUrl("/api/project/list", ""), "/api/project/list");
});
