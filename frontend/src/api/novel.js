import { post } from "./http";

export function generateArchives({ projectId, graphId, entityTypes, useLlm = false }) {
  return post("/api/novel/archives/generate", {
    project_id: projectId,
    graph_id: graphId,
    entity_types: entityTypes,
    use_llm: useLlm,
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
