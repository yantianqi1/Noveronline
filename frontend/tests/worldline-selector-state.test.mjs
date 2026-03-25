import test from "node:test";
import assert from "node:assert/strict";

import {
  buildProjectSessionOptions,
  isArchiveExpanded,
  toggleArchiveExpansion,
  toggleArchiveSelection,
} from "../src/views/shared/worldlineSelectorState.js";

test("toggleArchiveSelection adds a new archive and removes it on second click", () => {
  const archive = { archive_id: "archive_a", entity_name: "沈夜", project_id: "proj_1" };
  const added = toggleArchiveSelection([], archive);
  const removed = toggleArchiveSelection(added, archive);

  assert.deepEqual(added, [archive]);
  assert.deepEqual(removed, []);
});

test("toggleArchiveSelection replaces outdated record with latest archive payload", () => {
  const previous = [{ archive_id: "archive_a", entity_name: "旧沈夜", project_id: "proj_1" }];
  const next = toggleArchiveSelection(previous, {
    archive_id: "archive_a",
    entity_name: "沈夜",
    project_id: "proj_1",
  });

  assert.equal(next.length, 1);
  assert.equal(next[0].entity_name, "沈夜");
});

test("toggleArchiveSelection updates detail payload for the same archive without duplicating entries", () => {
  const previous = [{ archive_id: "archive_a", entity_name: "沈夜", project_id: "proj_1" }];
  const next = toggleArchiveSelection(previous, {
    archive_id: "archive_a",
    entity_name: "沈夜",
    project_id: "proj_1",
    core_drive: "查明失落剑谱",
  });

  assert.equal(next.length, 1);
  assert.equal(next[0].core_drive, "查明失落剑谱");
});

test("archive expansion remains independent from archive selection", () => {
  const selected = toggleArchiveSelection([], { archive_id: "archive_a", entity_name: "沈夜" });
  const expandedId = toggleArchiveExpansion("", "archive_b");

  assert.deepEqual(selected, [{ archive_id: "archive_a", entity_name: "沈夜" }]);
  assert.equal(isArchiveExpanded(expandedId, "archive_a"), false);
  assert.equal(isArchiveExpanded(expandedId, "archive_b"), true);
  assert.equal(toggleArchiveExpansion(expandedId, "archive_b"), "");
});

test("buildProjectSessionOptions groups global sessions separately from project sessions", () => {
  const options = buildProjectSessionOptions([
    { session_id: "ws_a", project_id: "proj_1", session_scope: "project", source_project_ids: ["proj_1"] },
    { session_id: "ws_b", project_id: null, session_scope: "global", source_project_ids: ["proj_1", "proj_2"] },
  ]);

  assert.deepEqual(options, [
    { value: "", label: "全部会话" },
    { value: "proj_1", label: "项目会话 · proj_1" },
    { value: "__global__", label: "全局混合会话" },
  ]);
});
