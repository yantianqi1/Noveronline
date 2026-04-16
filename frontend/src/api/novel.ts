/**
 * Novel API client — archive generation, seed analysis, chapter context, reviewer rules.
 */

import { get, post, put } from "@/api/http";
import type { ApiResponse } from "@/api/http";

/* ---------- Archive candidates & generation ---------- */

export interface GenerateArchiveCandidatesParams {
  projectId: string;
  graphId: string;
  entityTypes?: string[];
}

export function generateArchiveCandidates({
  projectId,
  graphId,
  entityTypes,
}: GenerateArchiveCandidatesParams): Promise<ApiResponse> {
  return post("/api/novel/archives/candidates", {
    project_id: projectId,
    graph_id: graphId,
    entity_types: entityTypes,
  });
}

export interface GenerateArchivesParams {
  projectId: string;
  graphId: string;
  entityTypes?: string[];
  useLlm?: boolean;
  tierOverrides?: unknown[];
  candidateSnapshot?: unknown[];
}

export function generateArchives({
  projectId,
  graphId,
  entityTypes,
  useLlm = false,
  tierOverrides = [],
  candidateSnapshot = [],
}: GenerateArchivesParams): Promise<ApiResponse> {
  return post("/api/novel/archives/generate", {
    project_id: projectId,
    graph_id: graphId,
    entity_types: entityTypes,
    use_llm: useLlm,
    tier_overrides: tierOverrides,
    candidate_snapshot: candidateSnapshot,
  });
}

/* ---------- Parallel world config ---------- */

export interface GenerateParallelWorldConfigParams {
  projectId: string;
  graphId: string;
  variables?: unknown[];
  entityTypes?: string[];
  branchCount?: number;
  focusQuestion?: string;
  useLlm?: boolean;
}

export function generateParallelWorldConfig({
  projectId,
  graphId,
  variables = [],
  entityTypes,
  branchCount,
  focusQuestion,
  useLlm = false,
}: GenerateParallelWorldConfigParams): Promise<ApiResponse> {
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

/* ---------- Seed analysis ---------- */

export interface RunSeedAnalysisParams {
  projectId: string;
  graphId: string;
  analysisGoal: string;
  maxCharacters?: number;
  maxOrganizations?: number;
}

export function runSeedAnalysis({
  projectId,
  graphId,
  analysisGoal,
  maxCharacters = 120,
  maxOrganizations = 80,
}: RunSeedAnalysisParams): Promise<ApiResponse> {
  const payload = {
    project_id: projectId,
    graph_id: graphId,
    analysis_goal: analysisGoal,
    max_characters: maxCharacters,
    max_organizations: maxOrganizations,
  };
  return post("/api/novel/seed-analysis", payload);
}

/* ---------- Chapter context ---------- */

export function getChapterContextOptions(projectId: string): Promise<ApiResponse> {
  return get(`/api/novel/chapter-context/options?project_id=${encodeURIComponent(projectId)}`);
}

export function buildChapterContext(payload: unknown): Promise<ApiResponse> {
  return post("/api/novel/chapter-context", payload);
}

/* ---------- Reviewer rules ---------- */

export function getReviewerRules(projectId: string): Promise<ApiResponse> {
  return get(`/api/novel/reviewer-rules?project_id=${encodeURIComponent(projectId)}`);
}

export function saveReviewerRules(
  projectId: string,
  customPrompt: string,
): Promise<ApiResponse> {
  return put("/api/novel/reviewer-rules", {
    project_id: projectId,
    custom_prompt: customPrompt,
  });
}
