import { get, post, put } from "./http.js";
import { postSSE } from "./sse.js";

export function generateArchiveCandidates({ projectId, graphId, entityTypes }) {
  return post("/api/novel/archives/candidates", {
    project_id: projectId,
    graph_id: graphId,
    entity_types: entityTypes,
  });
}

export function generateArchives({
  projectId,
  graphId,
  entityTypes,
  useLlm = false,
  tierOverrides = [],
  candidateSnapshot = [],
}) {
  return post("/api/novel/archives/generate", {
    project_id: projectId,
    graph_id: graphId,
    entity_types: entityTypes,
    use_llm: useLlm,
    tier_overrides: tierOverrides,
    candidate_snapshot: candidateSnapshot,
  });
}

export function generateParallelWorldConfig({
  projectId,
  graphId,
  variables = [],
  entityTypes,
  branchCount,
  focusQuestion,
  useLlm = false,
}) {
  return post("/api/novel/parallel-world/config", {
    project_id: projectId,
    graph_id: graphId,
    variables,
    entity_types: entityTypes,
    branch_count: branchCount,
    focus_question: focusQuestion,
    use_llm: useLlm,
  });
}

export function runSeedAnalysis({
  projectId,
  graphId,
  analysisGoal,
  maxCharacters = 120,
  maxOrganizations = 80,
}) {
  const payload = {
    project_id: projectId,
    graph_id: graphId,
    analysis_goal: analysisGoal,
    max_characters: maxCharacters,
    max_organizations: maxOrganizations,
  };
  return post("/api/novel/seed-analysis", payload);
}

export function getChapterContextOptions(projectId) {
  return get(`/api/novel/chapter-context/options?project_id=${encodeURIComponent(projectId)}`);
}

export function buildChapterContext(payload) {
  return post("/api/novel/chapter-context", payload);
}

/**
 * 多 Agent 协同生成小说正文（SSE 流式）。
 *
 * @param {object} payload - 请求体
 * @param {object} handlers - SSE 事件回调 { onEvent, onDone, onError }
 * @param {AbortSignal} [signal] - 可选取消信号
 */
export function generateDraft(payload, handlers, signal) {
  return postSSE("/api/novel/draft/generate", payload, handlers, signal);
}

export function getReviewerRules(projectId) {
  return get(`/api/novel/reviewer-rules?project_id=${encodeURIComponent(projectId)}`);
}

export function saveReviewerRules(projectId, customPrompt) {
  return put("/api/novel/reviewer-rules", {
    project_id: projectId,
    custom_prompt: customPrompt,
  });
}

/**
 * 用户驱动的修订流程（SSE 流式）。
 *
 * @param {object} payload - 请求体
 * @param {object} handlers - SSE 事件回调 { onEvent, onDone, onError }
 * @param {AbortSignal} [signal] - 可选取消信号
 */
export function reviseDraft(payload, handlers, signal) {
  return postSSE("/api/novel/draft/revise", payload, handlers, signal);
}
