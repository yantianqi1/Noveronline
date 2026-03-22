import test from "node:test";
import assert from "node:assert/strict";

import {
  buildArchiveLibraryDetailPath,
  buildArchiveLibraryListPath,
  listArchiveLibrary,
} from "../src/api/archive.js";

test("buildArchiveLibraryListPath omits empty filters", () => {
  assert.equal(buildArchiveLibraryListPath(), "/api/archive/library");
});

test("buildArchiveLibraryListPath encodes search filters and pagination", () => {
  const path = buildArchiveLibraryListPath({
    q: "沈夜",
    projectId: "proj_demo",
    entityType: "Character",
    importanceTier: "major",
    limit: 30,
    offset: 10,
  });

  assert.equal(
    path,
    "/api/archive/library?q=%E6%B2%88%E5%A4%9C&project_id=proj_demo&entity_type=Character&importance_tier=major&limit=30&offset=10",
  );
});

test("buildArchiveLibraryDetailPath returns the detail endpoint", () => {
  assert.equal(buildArchiveLibraryDetailPath("archive_demo"), "/api/archive/library/archive_demo");
});

test("listArchiveLibrary requests the computed endpoint with GET", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: { items: [] } };
      },
    };
  };

  try {
    await listArchiveLibrary({ q: "玄霄宗", projectId: "proj_1" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 1);
  assert.match(String(calls[0].url), /\/api\/archive\/library\?q=.*project_id=proj_1$/);
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.cache, "no-store");
});
