import type { StoryGraphBondGenerationSummary, StoryGraphBuildSummary } from "../lib/api";
import { type Locale, tx } from "../lib/locale";

export function storyGraphBuildStatus(result: StoryGraphBuildSummary, locale: Locale) {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
      runId: "",
    };
  }
  return {
    status: "success",
    code: "STORY_GRAPH_BUILD_QUEUED",
    message: tx(locale, "图谱构建任务已加入队列", "Story graph build queued"),
    runId: result.run_id,
  };
}

export function storyGraphBondStatus(result: StoryGraphBondGenerationSummary, locale: Locale) {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
      runId: "",
    };
  }
  return {
    status: "success",
    code: "STORY_GRAPH_BOND_QUEUED",
    message: tx(locale, "关系生成任务已加入队列", "Bond generation queued"),
    runId: result.run_id,
  };
}
