import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  ARCHIVE_LIBRARY_DESKTOP_BREAKPOINT,
  ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP,
  ARCHIVE_LIBRARY_LAYOUT_MODE_STACKED,
  ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO,
  ARCHIVE_LIBRARY_SPLIT_MAX_RATIO,
  ARCHIVE_LIBRARY_SPLIT_MIN_RATIO,
  clampArchiveLibrarySplitRatio,
  resolveArchiveLibraryLayoutMode,
  restoreArchiveLibrarySplitRatio,
} from "../src/views/shared/archiveLibraryLayout.js";

test("resolveArchiveLibraryLayoutMode keeps wide containers in desktop mode", () => {
  assert.equal(
    resolveArchiveLibraryLayoutMode(ARCHIVE_LIBRARY_DESKTOP_BREAKPOINT),
    ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP,
  );
  assert.equal(resolveArchiveLibraryLayoutMode(960), ARCHIVE_LIBRARY_LAYOUT_MODE_STACKED);
});

test("restoreArchiveLibrarySplitRatio returns the default ratio when storage is empty", () => {
  assert.equal(restoreArchiveLibrarySplitRatio(null, 1440), ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
});

test("clampArchiveLibrarySplitRatio enforces desktop ratio limits", () => {
  assert.equal(
    clampArchiveLibrarySplitRatio(0.1, 1440),
    ARCHIVE_LIBRARY_SPLIT_MIN_RATIO,
  );
  assert.equal(
    clampArchiveLibrarySplitRatio(0.9, 1440),
    ARCHIVE_LIBRARY_SPLIT_MAX_RATIO,
  );
});

test("restoreArchiveLibrarySplitRatio clamps persisted values into the allowed range", () => {
  assert.equal(restoreArchiveLibrarySplitRatio("0.46", 1440), 0.46);
  assert.equal(
    restoreArchiveLibrarySplitRatio("0.9", 1440),
    ARCHIVE_LIBRARY_SPLIT_MAX_RATIO,
  );
});

test("stacked mode always falls back to the default ratio", () => {
  assert.equal(restoreArchiveLibrarySplitRatio("0.56", 960), ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
  assert.equal(clampArchiveLibrarySplitRatio(0.56, 960), ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
});

test("restoreArchiveLibrarySplitRatio falls back to the default ratio for invalid values", () => {
  assert.equal(
    restoreArchiveLibrarySplitRatio("not-a-number", 1440),
    ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO,
  );
});

test("archive card click uses toggle as the primary selection action", async () => {
  const source = await readFile(new URL("../src/components/ArchiveLibraryGridItem.vue", import.meta.url), "utf8");

  assert.match(source, /<article[\s\S]*@click="\$emit\('toggle'\)"/);
  assert.doesNotMatch(source, /@click="\$emit\('select'\)"/);
});

test("archive card keeps a dedicated expand action separate from selection", async () => {
  const source = await readFile(new URL("../src/components/ArchiveLibraryGridItem.vue", import.meta.url), "utf8");

  assert.match(source, /@click\.stop="\$emit\('expand'\)"/);
  assert.match(source, /展开详情/);
});

test("archive card no longer uses join-session copy as the main selection entrance", async () => {
  const source = await readFile(new URL("../src/components/ArchiveLibraryGridItem.vue", import.meta.url), "utf8");

  assert.doesNotMatch(source, /加入会话/);
});
