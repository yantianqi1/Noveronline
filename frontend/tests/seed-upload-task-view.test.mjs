import test from "node:test";
import assert from "node:assert/strict";

import {
  buildIdleLogPreview,
  deriveStageProgress,
  normalizeSeedTaskDetail,
} from "../src/views/overview/seedUploadTaskView.js";
import { buildFailedTask, buildUploadingTask } from "../src/composables/seedUploadTaskState.js";

test("normalizeSeedTaskDetail preserves structured progress detail", () => {
  const normalized = normalizeSeedTaskDetail({
    status: "processing",
    progress: 52,
    created_at: "2026-03-21T12:00:00",
    progress_detail: {
      stage: "extract_local_facts",
      stage_label: "正在并发提取块内局部事实",
      active_stage: {
        key: "extract_local_facts",
        label: "正在并发提取块内局部事实",
        progress: 52,
        status: "processing",
      },
      task_metrics: {
        chapter_count: 12,
        block_count: 3,
        completed_blocks: 1,
        total_blocks: 3,
        active_workers: 2,
      },
      llm_activity: {
        enabled: true,
        mode: "llm",
        model: "gpt-4.1",
        action: "正在抽取块内事实",
        target_type: "block",
        target_label: "block_0002",
      },
      timeline: [
        {
          id: "evt_1",
          timestamp: "2026-03-21T12:00:01",
          stage: "extract_local_facts",
          level: "info",
          status: "active",
          title: "开始处理 block_0002",
          detail: "当前块覆盖第 11-12 章",
          meta: {
            block_id: "block_0002",
          },
        },
      ],
    },
  });

  assert.equal(normalized.activeStage.key, "extract_local_facts");
  assert.equal(normalized.taskMetrics.activeWorkers, 2);
  assert.equal(normalized.llmActivity.model, "gpt-4.1");
  assert.equal(normalized.timeline[0].meta.block_id, "block_0002");
});

test("normalizeSeedTaskDetail rejects legacy task payloads without structured detail", () => {
  assert.throws(
    () =>
      normalizeSeedTaskDetail({
        status: "processing",
        progress: 30,
        created_at: "2026-03-21T12:00:00",
        message: "文件已上传，后台正在分析小说...",
        progress_detail: {
          stage: "segment_chapters",
          stage_label: "正在切分章节与叙事段",
        },
      }),
    /structured progress_detail/i,
  );
});

test("normalizeSeedTaskDetail rejects camelCase compatibility payloads", () => {
  assert.throws(
    () =>
      normalizeSeedTaskDetail({
        status: "processing",
        progress: 30,
        created_at: "2026-03-21T12:00:00",
        progress_detail: {
          stage: "segment_chapters",
          stage_label: "正在切分章节与叙事段",
          active_stage: {
            key: "segment_chapters",
            label: "正在切分章节与叙事段",
            progress: 30,
            status: "processing",
          },
          task_metrics: {
            chapterCount: 2,
            blockCount: 1,
            completedBlocks: 0,
            totalBlocks: 1,
            activeWorkers: 1,
          },
          llm_activity: {
            enabled: true,
            mode: "llm",
            model: "gpt-5.4",
            action: "正在分析",
            targetType: "block",
            targetLabel: "block_0001",
          },
          timeline: [],
        },
      }),
    /structured progress_detail/i,
  );
});

test("normalizeSeedTaskDetail rejects payloads without timeline array", () => {
  assert.throws(
    () =>
      normalizeSeedTaskDetail({
        status: "processing",
        progress: 30,
        created_at: "2026-03-21T12:00:00",
        progress_detail: {
          stage: "segment_chapters",
          stage_label: "正在切分章节与叙事段",
          active_stage: {
            key: "segment_chapters",
            label: "正在切分章节与叙事段",
            progress: 30,
            status: "processing",
          },
          task_metrics: {
            chapter_count: 2,
            block_count: 1,
            completed_blocks: 0,
            total_blocks: 1,
            active_workers: 1,
          },
          llm_activity: {
            enabled: true,
            mode: "llm",
            model: "gpt-5.4",
            action: "正在分析",
            target_type: "block",
            target_label: "block_0001",
          },
        },
      }),
    /structured progress_detail/i,
  );
});

test("buildIdleLogPreview returns ordered pipeline preview", () => {
  const preview = buildIdleLogPreview();

  assert.equal(preview.length >= 5, true);
  assert.equal(preview[0].status, "pending");
  assert.equal(typeof preview[0].title, "string");
  assert.equal(preview.some((item) => item.stage === "chapter_card_generation"), true);
});

test("buildUploadingTask produces structured progress detail accepted by normalizeSeedTaskDetail", () => {
  const normalized = normalizeSeedTaskDetail(
    buildUploadingTask(
      "2026-03-21T12:00:00",
      10,
      "开始上传文件",
      "文件正在发送到后端",
    ),
  );

  assert.equal(normalized.activeStage.key, "uploading");
  assert.equal(normalized.taskMetrics.totalBlocks, 0);
  assert.equal(normalized.llmActivity.action, "等待开始分析");
});

test("buildFailedTask produces structured progress detail accepted by normalizeSeedTaskDetail", () => {
  const normalized = normalizeSeedTaskDetail(
    buildFailedTask(
      "2026-03-21T12:00:00",
      10,
      "上传失败",
    ),
  );

  assert.equal(normalized.activeStage.key, "failed");
  assert.equal(normalized.taskMetrics.activeWorkers, 0);
  assert.equal(normalized.llmActivity.action, "上传失败");
});

test("deriveStageProgress tracks per-chapter progress during chapter card generation", () => {
  const progress = deriveStageProgress(
    {
      key: "chapter_card_generation",
      label: "正在逐章生成结构化章节卡",
      progress: 78,
      status: "processing",
    },
    {
      chapterCount: 4,
      blockCount: 0,
      completedBlocks: 0,
      totalBlocks: 0,
      activeWorkers: 0,
    },
    [
      {
        id: "evt_ch1",
        timestamp: "2026-03-29T23:10:00",
        stage: "chapter_card_generation",
        level: "info",
        status: "completed",
        title: "完成第1章章节卡",
        detail: "第 1 章章节卡",
        meta: { chapter_order: 1 },
      },
      {
        id: "evt_ch2",
        timestamp: "2026-03-29T23:11:00",
        stage: "chapter_card_generation",
        level: "info",
        status: "completed",
        title: "完成第2章章节卡",
        detail: "第 2 章章节卡",
        meta: { chapter_order: 2 },
      },
    ],
  );

  assert.equal(progress.detail, "2/4 章");
  assert.equal(progress.percent, 80);
});

test("deriveStageProgress reuses block counters for block-based stages", () => {
  const progress = deriveStageProgress(
    {
      key: "extract_local_facts",
      label: "正在并发提取块内局部事实",
      progress: 50,
      status: "processing",
    },
    {
      chapterCount: 12,
      blockCount: 6,
      completedBlocks: 3,
      totalBlocks: 6,
      activeWorkers: 2,
    },
    [],
  );

  assert.equal(progress.detail, "3/6 块");
  assert.equal(progress.percent, 54);
});
