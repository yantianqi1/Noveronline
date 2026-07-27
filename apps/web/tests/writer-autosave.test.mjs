import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../app/projects/[projectId]/writer/writer-workspace.tsx", import.meta.url),
  "utf8",
);

function functionBody(name, nextMarker) {
  const start = source.indexOf(`function ${name}`);
  const end = source.indexOf(nextMarker, start);
  assert.notEqual(start, -1, `${name} must exist`);
  assert.notEqual(end, -1, `${name} boundary must exist`);
  return source.slice(start, end);
}

test("chapter switches await pending manuscript saves before changing chapter", () => {
  const body = functionBody("handleSelectChapter", "// ── W2:");
  const flush = body.indexOf("await flushPendingSegmentSaves()")
  const switchChapter = body.indexOf("setActiveChapterId(chapterId)");
  assert.ok(flush >= 0 && switchChapter > flush);
});

test("new chapter and draft adoption both fail closed when manuscript save fails", () => {
  const newChapter = functionBody("handleNewChapter", "async function handleSelectChapter");
  const adopt = functionBody("handleAdopt", "return (");
  assert.match(newChapter, /if \(!\(await flushPendingSegmentSaves\(\)\)\)/);
  assert.match(adopt, /if \(!\(await flushPendingSegmentSaves\(\)\)\)/);
  assert.ok(newChapter.indexOf("flushPendingSegmentSaves") < newChapter.indexOf("createChapter("));
  assert.ok(adopt.indexOf("flushPendingSegmentSaves") < adopt.indexOf("adoptDraft("));
});

test("debounced saves leave the timer map before joining the serialized save queue", () => {
  assert.match(source, /timers\.delete\(blockId\);\s*void queueSegmentSave\(blockId\);/);
  assert.match(source, /const previous = savePromisesRef\.current\.get\(blockId\)/);
});
