import test from "node:test";
import assert from "node:assert/strict";

import {
  buildProjectSessionOptions,
  resolveSelectedBranchId,
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

test("resolveSelectedBranchId keeps the current branch when it still exists", () => {
  const branches = [
    { branch_id: "branch_a" },
    { branch_id: "branch_b" },
  ];
  assert.equal(resolveSelectedBranchId(branches, "branch_b"), "branch_b");
});

test("resolveSelectedBranchId falls back to the first branch when current branch is missing", () => {
  const branches = [
    { branch_id: "branch_a" },
    { branch_id: "branch_b" },
  ];
  assert.equal(resolveSelectedBranchId(branches, "branch_x"), "branch_a");
  assert.equal(resolveSelectedBranchId([], "branch_x"), "");
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
