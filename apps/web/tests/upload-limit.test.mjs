import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

test("source upload BFF bounds request reads before buffering", async () => {
  const route = await readFile(
    path.join(root, "app/api/uploads/[uploadId]/object/route.ts"),
    "utf8",
  );

  assert.doesNotMatch(route, /request\.arrayBuffer\(\)/);
  assert.match(route, /MIROFISH_SOURCE_UPLOAD_MAX_BYTES/);
  assert.match(route, /request\.body\.getReader\(\)/);
  assert.match(route, /total > maxBytes/);
  assert.match(route, /SOURCE_FILE_OBJECT_TOO_LARGE/);
  assert.match(route, /status: 413/);
});
