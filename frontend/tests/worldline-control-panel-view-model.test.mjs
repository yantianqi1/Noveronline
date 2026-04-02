import test from "node:test";
import assert from "node:assert/strict";

import {
  buildWorldlineSessionSummary,
  countWorldlineVariables,
  resolvePrepareTaskMessage,
  resolveWorldlineSessionStatus,
} from "../src/views/worldline/worldlineControlPanelViewModel.js";

test("countWorldlineVariables ignores blank lines", () => {
  assert.equal(countWorldlineVariables(" 变量A \n\n变量B\n "), 2);
});

test("resolveWorldlineSessionStatus prefers error state", () => {
  assert.deepEqual(
    resolveWorldlineSessionStatus({ sessionId: "", error: "网络错误" }),
    { label: "整备失败", tone: "danger" },
  );
});

test("resolveWorldlineSessionStatus keeps runtime error label after session creation", () => {
  assert.deepEqual(
    resolveWorldlineSessionStatus({ sessionId: "session-1", error: "网络错误" }),
    { label: "操作异常", tone: "danger" },
  );
});

test("resolveWorldlineSessionStatus returns ok after session creation", () => {
  assert.deepEqual(
    resolveWorldlineSessionStatus({ sessionId: "session-1", error: "" }),
    { label: "会话已启动", tone: "ok" },
  );
});

test("buildWorldlineSessionSummary composes selected archives and variables", () => {
  assert.deepEqual(
    buildWorldlineSessionSummary({
      selectedArchives: [{ archive_id: "a" }, { archive_id: "b" }],
      variablesText: "变量A\n变量B",
      sessionId: "",
      sessionScope: "",
    }),
    [
      { label: "已选档案", value: "2 份" },
      { label: "初始变量", value: "2 条" },
      { label: "会话范围", value: "待创建" },
    ],
  );
});

test("buildWorldlineSessionSummary exposes readable session scope", () => {
  assert.deepEqual(
    buildWorldlineSessionSummary({
      selectedArchives: [{ archive_id: "a" }],
      variablesText: "变量A",
      sessionId: "session-1",
      sessionScope: "global",
    }),
    [
      { label: "已选档案", value: "1 份" },
      { label: "初始变量", value: "1 条" },
      { label: "会话范围", value: "全局混合会话" },
    ],
  );
});

test("resolvePrepareTaskMessage prefers prepare error details", () => {
  assert.equal(
    resolvePrepareTaskMessage({
      prepareSnapshot: {
        status: "failed",
        error: "世界线 Agent 整备 未配置 LLM 渠道和模型",
      },
      error: "世界线 prepare 失败",
    }),
    "世界线 Agent 整备 未配置 LLM 渠道和模型",
  );
});

test("resolvePrepareTaskMessage falls back to task message while preparing", () => {
  assert.equal(
    resolvePrepareTaskMessage({
      prepareSnapshot: {
        status: "preparing",
        task_message: "世界线 prepare：正在整备 agent",
      },
      error: "",
    }),
    "世界线 prepare：正在整备 agent",
  );
});
