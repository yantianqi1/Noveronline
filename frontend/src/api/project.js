import { del, get, post, uploadForm } from "./http.js";

export function buildProjectDeletePath(projectId) {
  return `/api/project/${projectId}`;
}

export function listProjects(limit = 20) {
  return get(`/api/project/list?limit=${limit}`);
}

export function getProject(projectId) {
  return get(`/api/project/${projectId}`);
}

export function getProjectGraph(projectId) {
  return get(`/api/project/${projectId}/graph`);
}

export function deleteProject(projectId) {
  return del(buildProjectDeletePath(projectId));
}

export function buildGraph(projectId, graphName = "Novel Story Graph") {
  return post("/api/project/build-graph", {
    project_id: projectId,
    graph_name: graphName,
  });
}

export function getTask(taskId) {
  return get(`/api/project/task/${taskId}`);
}

export function uploadStorySeed({
  projectName,
  analysisGoal,
  additionalContext,
  files = [],
  onProgress,
  onRequest,
}) {
  const formData = new FormData();
  formData.append("project_name", projectName);
  formData.append("analysis_goal", analysisGoal);
  formData.append("additional_context", additionalContext || "");
  for (const file of files) {
    formData.append("files", file);
  }
  return uploadForm("/api/project/seed/extract", formData, { onProgress, onRequest });
}
