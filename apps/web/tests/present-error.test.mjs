import assert from "node:assert/strict";
import test from "node:test";

import { presentError } from "../lib/present-error.ts";
import { presentRunMessage, reduceSeedProgress } from "../lib/api/seed.ts";

test("presentError maps the retryable code to Chinese", () => {
  const err = Object.assign(new Error("workflow run is not retryable"), { code: "WORKFLOW_RETRY_NOT_ALLOWED" });
  assert.equal(presentError(err, "重试失败。"), "这次分析暂时重试不了。请刷新页面看最新状态；若仍是失败，稍后重试或重新上传。");
});

test("presentError localizes known English messages without a code", () => {
  assert.equal(
    presentError(new Error("runtime facts write failed"), "失败。"),
    "写入故事事实失败。已读出的部分不会丢，修好后可重试。",
  );
});

test("presentError keeps already-Chinese messages and falls back on unknown English", () => {
  assert.equal(presentError(new Error("上传失败，请重试。"), "x"), "上传失败，请重试。");
  assert.equal(presentError(new Error("some totally unknown backend error"), "重试失败。"), "重试失败。");
});

test("presentRunMessage hides technical status lines and localizes failures", () => {
  assert.equal(presentRunMessage("seed stage sequential_reading completed"), "");
  assert.equal(presentRunMessage("seed stage persist_runtime_facts failed"), "分析在这一步失败了");
  assert.equal(presentRunMessage("runtime facts write failed"), "写入故事事实失败。已读出的部分不会丢，修好后可重试。");
});

test("reduceSeedProgress presents a failed stage's English error in Chinese", () => {
  const run = { run_id: "r1", status: "failed", progress: 42, message: "" };
  const events = [
    { event_type: "seed.stage.failed", payload: { stage: "persist_runtime_facts", error_message: "runtime facts write failed" } },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.terminal, "failed");
  assert.equal(progress.headline, "写入故事事实失败。已读出的部分不会丢，修好后可重试。");
});

test("reduceSeedProgress marks a still-running run with a failed stage as stalled, not failed", () => {
  // Backend lag/loss: the stage reported failure but the run row still says
  // "running". The reducer must NOT claim "failed" — the backend would refuse
  // a retry while the run is marked running, so the UI must not offer one.
  const run = { run_id: "r1", status: "running", progress: 62, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.stage.failed", payload: { stage: "global_aggregation", error_message: "global aggregation output schema validation failed" } },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.terminal, "stalled");
  assert.equal(progress.headline, "分析返回的内容格式不正确。这通常是模型输出不稳定，可重试。");
});

test("reduceSeedProgress recovers to running when a failed stage is retried and re-activated", () => {
  // Regression: a run that failed sequential_reading, then was retried and is
  // now reading again, must render as running — not stuck on "已卡住".
  const run = { run_id: "r1", status: "running", progress: 38, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.stage.pending", payload: { stage: "sequential_reading", message: "开始顺序精读（共 302 段）" } },
    { event_type: "seed.stage.failed", payload: { stage: "sequential_reading", error_code: "LLM_PROVIDER_ERROR", error_message: "sequential reading failed" } },
    { event_type: "workflow.retry_requested", payload: { status: "retry_requested" } },
    { event_type: "seed.stage.pending", payload: { stage: "parse_file" } },
    { event_type: "seed.stage.completed", payload: { stage: "parse_file" } },
    { event_type: "seed.stage.pending", payload: { stage: "sequential_reading", message: "开始顺序精读（共 302 段）" } },
    { event_type: "seed.sequential_reading.progress", payload: { completed_segments: 100, total_segments: 302, message: "开始精读 75-100/302 · 阁老" } },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.terminal, "running");
  assert.equal(progress.percent, 38);
  const reading = progress.stages.find((s) => s.key === "sequential_reading");
  assert.equal(reading.status, "active");
  assert.equal(progress.headline, "开始精读 75-100/302 · 阁老");
});

test("reduceSeedProgress stays stalled when a stage fails and never recovers", () => {
  // A failure with no subsequent retry/re-activation is the genuine wedged case.
  const run = { run_id: "r1", status: "running", progress: 10, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.stage.pending", payload: { stage: "parse_file" } },
    { event_type: "seed.stage.completed", payload: { stage: "parse_file" } },
    { event_type: "seed.stage.failed", payload: { stage: "segment_text", error_message: "segment text failed" } },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.terminal, "stalled");
});
