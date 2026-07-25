import type { SeedRun, WorkflowEvent } from "@/lib/api/overview-types";

/**
 * Seed-pipeline domain logic: stage metadata, event → progress reduction, and
 * display labels. Pure functions so they're testable and framework-free.
 *
 * The Go API exposes runs (status/progress/message) and a JSON-pollable event
 * stream (`GET .../seed-runs/{id}/events?after_event_id=N`). We reduce those
 * events into a per-stage view model the UI renders as a scroll of stages.
 */

/** Present a backend English error message to the author in Chinese. */
const SEED_ERROR_MESSAGES: Array<[RegExp, string]> = [
  [/runtime facts write failed/i, "写入故事事实失败。已读出的部分不会丢，修好后可重试。"],
  [/reading notes write failed/i, "写入精读笔记失败。已读出的部分不会丢，修好后可重试。"],
  [/schema validation/i, "分析返回的内容格式不正确。这通常是模型输出不稳定，可重试。"],
  [/not retryable/i, "这次分析暂时重试不了。请刷新页面看最新状态；若仍是失败，稍后重试或重新上传。"],
  [/unconfigured/i, "分析服务未配置好，请联系管理员。"],
];

function presentSeedError(message: string): string {
  if (!message) return message;
  if (/[一-鿿]/.test(message)) return message; // already Chinese
  for (const [pattern, localized] of SEED_ERROR_MESSAGES) {
    if (pattern.test(message)) return localized;
  }
  return "分析在这一步失败了。已读出的部分不会丢，可查看日志或重试。";
}

/** Public: localize a run's backend status/error message for the activity rail. */
export function presentRunMessage(message: string | null | undefined): string {
  if (!message) return "";
  // Status lines like "seed stage X failed/completed" are technical, not author copy.
  const stageMatch = /^seed stage .+? (failed|completed|running)$/i.exec(message.trim());
  if (stageMatch) {
    return stageMatch[1].toLowerCase() === "failed" ? "分析在这一步失败了" : "";
  }
  return presentSeedError(message);
}

/** The canonical Seed stage sequence, as emitted by the agent runtime. */
export const SEED_STAGES = [
  "parse_file",
  "segment_text",
  "sequential_reading",
  "global_aggregation",
  "story_ontology",
  "agent_profiles",
  "entity_resolution",
  "archive_candidates",
  "index_assets",
  "persist_runtime_facts",
  "finalize",
] as const;

export type SeedStageKey = (typeof SEED_STAGES)[number];

export const SEED_STAGE_LABELS: Record<string, string> = {
  parse_file: "解析原文",
  segment_text: "切分段落",
  sequential_reading: "顺序精读",
  global_aggregation: "全局聚合",
  story_ontology: "故事本体",
  agent_profiles: "角色档案",
  entity_resolution: "实体归并",
  archive_candidates: "档案候选",
  index_assets: "资产索引",
  persist_runtime_facts: "写入事实",
  finalize: "收尾",
};

export function stageLabel(stage: string): string {
  return SEED_STAGE_LABELS[stage] ?? stage;
}

export type StageStatus = "pending" | "active" | "completed" | "failed";

export type StageView = {
  key: string;
  label: string;
  status: StageStatus;
};

export type SequentialReadingProgress = {
  completed: number;
  total: number;
  message: string;
  chapterGuess?: string;
};

/** Per-batch progress for an enrichment stage (agent_profiles / archive_candidates). */
export type EnrichmentProgress = {
  completed: number;
  total: number;
  message: string;
};

export type SeedProgress = {
  stages: StageView[];
  /** Index into stages of the currently-active (or last-active) stage. */
  activeIndex: number;
  /** 0–100 overall completion estimate. */
  percent: number;
  /** Latest human-facing status line. */
  headline: string;
  sequentialReading: SequentialReadingProgress | null;
  /** Live per-batch progress for character profile generation, if running. */
  agentProfiles: EnrichmentProgress | null;
  /** Live per-batch progress for archive candidate generation, if running. */
  archiveCandidates: EnrichmentProgress | null;
  terminal: "running" | "failed" | "cancelled" | "completed" | "stalled";
};

/**
 * Reduce a run's events (and the run's own status) into a progress view model.
 * Events carry the granular per-stage transitions; the run status is the
 * authoritative terminal state.
 */
export function reduceSeedProgress(run: SeedRun | null, events: WorkflowEvent[]): SeedProgress {
  const stageStatus = new Map<string, StageStatus>();
  let sequentialReading: SequentialReadingProgress | null = null;
  let agentProfiles: EnrichmentProgress | null = null;
  let archiveCandidates: EnrichmentProgress | null = null;
  let headline = "";
  // Stage keys that reported a failure and have NOT shown signs of life since.
  // Tracked as a set so a retry that re-activates (or completes) the stage
  // clears the stale failure instead of leaving the run looking wedged.
  const failedStages = new Set<string>();

  for (const event of events) {
    const payload = event.payload ?? {};
    const stage = typeof payload.stage === "string" ? payload.stage : "";

    switch (event.event_type) {
      case "seed.stage.pending":
        if (stage) {
          stageStatus.set(stage, "active");
          // A re-pended stage is alive again — clear any earlier failure.
          failedStages.delete(stage);
        }
        if (typeof payload.message === "string") headline = payload.message;
        break;
      case "seed.stage.completed":
        if (stage) {
          stageStatus.set(stage, "completed");
          failedStages.delete(stage);
          // The stage is done: retire its live sub-progress so the strip
          // unmounts. Panels only clear these while `running` (AnimatePresence
          // exit), so on a fast terminal transition a never-cleared strip would
          // freeze mid-flight (e.g. the reading bar stuck at 20/20).
          if (stage === "sequential_reading") sequentialReading = null;
          else if (stage === "agent_profiles") agentProfiles = null;
          else if (stage === "archive_candidates") archiveCandidates = null;
        }
        break;
      case "seed.stage.failed":
        if (stage) {
          stageStatus.set(stage, "failed");
          failedStages.add(stage);
        }
        if (typeof payload.error_message === "string") headline = presentSeedError(payload.error_message);
        break;
      case "seed.sequential_reading.progress": {
        const completed = numberOr(payload.completed_segments, 0);
        const total = numberOr(payload.total_segments, 0);
        stageStatus.set("sequential_reading", "active");
        // Live reading progress means a prior sequential_reading failure was retried.
        failedStages.delete("sequential_reading");
        sequentialReading = {
          completed,
          total,
          message: typeof payload.message === "string" ? payload.message : "",
          chapterGuess:
            typeof payload.chapter_guess === "string" ? payload.chapter_guess : undefined,
        };
        if (sequentialReading.message) headline = sequentialReading.message;
        break;
      }
      case "seed.agent_profiles.progress": {
        stageStatus.set("agent_profiles", "active");
        failedStages.delete("agent_profiles");
        agentProfiles = {
          completed: numberOr(payload.completed_entities, 0),
          total: numberOr(payload.total_entities, 0),
          message: typeof payload.message === "string" ? payload.message : "",
        };
        if (agentProfiles.message) headline = agentProfiles.message;
        break;
      }
      case "seed.archive_candidates.progress": {
        stageStatus.set("archive_candidates", "active");
        failedStages.delete("archive_candidates");
        archiveCandidates = {
          completed: numberOr(payload.completed_entities, 0),
          total: numberOr(payload.total_entities, 0),
          message: typeof payload.message === "string" ? payload.message : "",
        };
        if (archiveCandidates.message) headline = archiveCandidates.message;
        break;
      }
      case "workflow.retry_requested":
        // The author asked to retry: any earlier stage failure is superseded by
        // the fresh attempt. Clear failure state so a healthy retry renders as
        // running, not stalled. (If the retry never re-activates a stage, the
        // run stays live with no failed stage — also not "stalled".)
        failedStages.clear();
        for (const [key, value] of stageStatus) {
          if (value === "failed") stageStatus.set(key, "pending");
        }
        break;
      case "workflow.failed":
      case "workflow.start_failed":
        // Whole-run failure: mark every unresolved stage as failed-attention.
        failedStages.add("__run__");
        if (typeof payload.error_message === "string") headline = presentSeedError(payload.error_message);
        break;
      default:
        break;
    }
  }
  const sawFailure = failedStages.size > 0;

  // Resolve terminal state from the run status (authoritative) then events.
  const status = (run?.status ?? "").toLowerCase();
  const live = status === "running" || status === "queued" || status === "pending" || status === "in_progress";
  let terminal: SeedProgress["terminal"] = "running";
  if (status === "failed" || status === "error") terminal = "failed";
  else if (status === "cancelled" || status === "canceled") terminal = "cancelled";
  else if (status === "completed" || status === "succeeded" || status === "success") {
    terminal = "completed";
  } else if (sawFailure && live) {
    // A stage reported failure but the run row still says "running" — the
    // status write is lagging (or was lost). Surface this as "stalled", not
    // "failed": the backend will refuse a retry while the run is still marked
    // running, so offering a retry button here would be a lie.
    terminal = "stalled";
  } else if (sawFailure) {
    terminal = "failed";
  }

  // Build the ordered stage view. When complete, mark every stage done.
  let activeIndex = -1;
  const stages: StageView[] = SEED_STAGES.map((key, index) => {
    let s = stageStatus.get(key) ?? "pending";
    if (terminal === "completed") s = "completed";
    if (s === "active" && activeIndex === -1) activeIndex = index;
    return { key, label: stageLabel(key), status: s };
  });
  // A failed stage is "active" for display purposes (it's where attention goes).
  if (activeIndex === -1) {
    const failedIdx = stages.findIndex((s) => s.status === "failed");
    if (failedIdx !== -1) activeIndex = failedIdx;
  }

  // Overall percent. Only a successful run is ever "100%". While running we
  // trust the run's own progress; for failed/cancelled runs we show how far it
  // actually got (completed stages), because the API reports progress=100 even
  // on failure — showing a full bar for a failed run would be dishonest.
  let percent: number;
  if (terminal === "completed") {
    percent = 100;
  } else if (terminal === "running") {
    const done = stages.filter((s) => s.status === "completed").length;
    const derived = Math.round((done / SEED_STAGES.length) * 100);
    percent =
      typeof run?.progress === "number" && run.progress > 0 && run.progress < 100
        ? run.progress
        : derived;
  } else {
    // failed / cancelled — reflect real, partial completion.
    const done = stages.filter((s) => s.status === "completed").length;
    percent = Math.round((done / SEED_STAGES.length) * 100);
  }

  // Fallback headline.
  if (!headline) {
    if (terminal === "completed") headline = "分析完成，故事素材已就绪。";
    else if (terminal === "failed") headline = run?.error_message || "分析失败了，可以重试。";
    else if (terminal === "cancelled") headline = "分析已取消。";
    else if (terminal === "stalled") {
      headline = "分析中途卡住：进度状态没有更新。取消这次卡住的分析后，就能重新开始。";
    } else headline = run?.message || "正在分析…";
  }

  return { stages, activeIndex, percent, headline, sequentialReading, agentProfiles, archiveCandidates, terminal };
}

function numberOr(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/** Short, human label for a run's status chip. */
export function runStatusLabel(run: SeedRun): string {
  const status = run.status.toLowerCase();
  if (status === "completed" || status === "succeeded") return "已完成";
  if (status === "failed" || status === "error") return "失败";
  if (status === "cancelled" || status === "canceled") return "已取消";
  if (status === "queued") return "排队中";
  return "进行中";
}
