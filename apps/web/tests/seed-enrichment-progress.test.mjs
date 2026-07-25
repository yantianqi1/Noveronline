import assert from "node:assert/strict";
import test from "node:test";

import { reduceSeedProgress } from "../lib/api/seed.ts";

// Doc 42 §7.2-2: batched enrichment emits seed.agent_profiles.progress /
// seed.archive_candidates.progress events. The reducer must surface them as
// {completed, total, message} sub-progress, mark the stage active, and lift the
// localized message into the headline.

test("reduceSeedProgress reduces agent_profiles batch progress into sub-progress", () => {
  const run = { run_id: "r1", status: "running", progress: 82, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.stage.pending", payload: { stage: "agent_profiles" } },
    {
      event_type: "seed.agent_profiles.progress",
      payload: {
        stage: "agent_profiles",
        completed_entities: 5,
        total_entities: 12,
        message: "正在生成角色档案 5/12 · 林舟",
      },
    },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.terminal, "running");
  assert.deepEqual(progress.agentProfiles, {
    completed: 5,
    total: 12,
    message: "正在生成角色档案 5/12 · 林舟",
  });
  assert.equal(progress.archiveCandidates, null);
  const stage = progress.stages.find((s) => s.key === "agent_profiles");
  assert.equal(stage.status, "active");
  assert.equal(progress.headline, "正在生成角色档案 5/12 · 林舟");
});

test("reduceSeedProgress reduces archive_candidates batch progress into sub-progress", () => {
  const run = { run_id: "r1", status: "running", progress: 88, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.stage.pending", payload: { stage: "archive_candidates" } },
    {
      event_type: "seed.archive_candidates.progress",
      payload: {
        stage: "archive_candidates",
        completed_entities: 10,
        total_entities: 20,
        message: "正在生成档案候选 10/20",
      },
    },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.deepEqual(progress.archiveCandidates, {
    completed: 10,
    total: 20,
    message: "正在生成档案候选 10/20",
  });
  assert.equal(progress.agentProfiles, null);
  const stage = progress.stages.find((s) => s.key === "archive_candidates");
  assert.equal(stage.status, "active");
  assert.equal(progress.headline, "正在生成档案候选 10/20");
});

test("reduceSeedProgress keeps the latest enrichment batch as it advances", () => {
  const run = { run_id: "r1", status: "running", progress: 85, message: "seed pipeline running" };
  const events = [
    {
      event_type: "seed.agent_profiles.progress",
      payload: { completed_entities: 5, total_entities: 12, message: "正在生成角色档案 5/12" },
    },
    {
      event_type: "seed.agent_profiles.progress",
      payload: { completed_entities: 10, total_entities: 12, message: "正在生成角色档案 10/12" },
    },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.agentProfiles.completed, 10);
  assert.equal(progress.agentProfiles.total, 12);
});

test("reduceSeedProgress clears a stale agent_profiles failure once batch progress resumes", () => {
  // A retried enrichment stage that starts emitting batch progress again must
  // render active/running, not stalled on the earlier failure.
  const run = { run_id: "r1", status: "running", progress: 82, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.stage.failed", payload: { stage: "agent_profiles", error_message: "profile failed" } },
    { event_type: "workflow.retry_requested", payload: { status: "retry_requested" } },
    {
      event_type: "seed.agent_profiles.progress",
      payload: { completed_entities: 5, total_entities: 12, message: "正在生成角色档案 5/12" },
    },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.terminal, "running");
  const stage = progress.stages.find((s) => s.key === "agent_profiles");
  assert.equal(stage.status, "active");
});

test("reduceSeedProgress defaults enrichment counts and tolerates a missing message", () => {
  const run = { run_id: "r1", status: "running", progress: 82, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.agent_profiles.progress", payload: { stage: "agent_profiles" } },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.deepEqual(progress.agentProfiles, { completed: 0, total: 0, message: "" });
});

test("reduceSeedProgress clears a stage's sub-progress once that stage completes", () => {
  // Regression: the reading bar stayed frozen at 20/20 into the character stage
  // because sequentialReading was only cleared while the run was still running.
  // A seed.stage.completed for the stage must retire its strip immediately.
  const run = { run_id: "r1", status: "running", progress: 60, message: "seed pipeline running" };
  const events = [
    { event_type: "seed.stage.pending", payload: { stage: "sequential_reading" } },
    {
      event_type: "seed.sequential_reading.progress",
      payload: { stage: "sequential_reading", completed_segments: 20, total_segments: 20, message: "完成精读 20/20" },
    },
    { event_type: "seed.stage.completed", payload: { stage: "sequential_reading" } },
    { event_type: "seed.stage.pending", payload: { stage: "agent_profiles" } },
    {
      event_type: "seed.agent_profiles.progress",
      payload: { stage: "agent_profiles", completed_entities: 5, total_entities: 41, message: "正在生成角色档案 5/41" },
    },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.sequentialReading, null);
  assert.equal(progress.stages.find((s) => s.key === "sequential_reading").status, "completed");
  assert.deepEqual(progress.agentProfiles, {
    completed: 5,
    total: 41,
    message: "正在生成角色档案 5/41",
  });
});

test("reduceSeedProgress clears enrichment sub-progress on its own completion", () => {
  const run = { run_id: "r1", status: "running", progress: 95, message: "seed pipeline running" };
  const events = [
    {
      event_type: "seed.agent_profiles.progress",
      payload: { stage: "agent_profiles", completed_entities: 40, total_entities: 41, message: "正在生成角色档案 40/41" },
    },
    { event_type: "seed.stage.completed", payload: { stage: "agent_profiles" } },
    {
      event_type: "seed.archive_candidates.progress",
      payload: { stage: "archive_candidates", completed_entities: 5, total_entities: 41, message: "正在生成叙事档案候选 5/41" },
    },
  ];
  const progress = reduceSeedProgress(run, events);
  assert.equal(progress.agentProfiles, null);
  assert.equal(progress.archiveCandidates.completed, 5);
});
