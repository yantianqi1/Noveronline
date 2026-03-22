import test from "node:test";
import assert from "node:assert/strict";

import {
  buildComparisonBranchIds,
  buildProjectSessionOptions,
  resolveSelectedBranchId,
  sanitizeCheckedBranchIds,
  toggleCheckedBranchId,
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

test("toggleCheckedBranchId adds and removes branch ids without mutating order", () => {
  const added = toggleCheckedBranchId([], "branch_a");
  const appended = toggleCheckedBranchId(added, "branch_b");
  const removed = toggleCheckedBranchId(appended, "branch_a");

  assert.deepEqual(added, ["branch_a"]);
  assert.deepEqual(appended, ["branch_a", "branch_b"]);
  assert.deepEqual(removed, ["branch_b"]);
});

test("sanitizeCheckedBranchIds drops stale ids and preserves branch list order", () => {
  const branches = [
    { branch_id: "branch_b" },
    { branch_id: "branch_a" },
    { branch_id: "branch_c" },
  ];

  assert.deepEqual(
    sanitizeCheckedBranchIds(branches, ["branch_x", "branch_a", "branch_b", "branch_a"]),
    ["branch_b", "branch_a"],
  );
});

test("buildComparisonBranchIds falls back to current branch when no branch is checked", () => {
  assert.deepEqual(buildComparisonBranchIds([], "branch_a"), ["branch_a"]);
  assert.deepEqual(buildComparisonBranchIds([], ""), []);
});

test("buildComparisonBranchIds prefers checked branches over current branch", () => {
  assert.deepEqual(buildComparisonBranchIds(["branch_c", "branch_a"], "branch_b"), ["branch_c", "branch_a"]);
});
