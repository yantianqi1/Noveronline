/**
 * Project API client — project lifecycle, graph building, task tracking, seed upload.
 */

import { del, get, post, uploadForm } from "@/api/http";
import type { ApiResponse, UploadProgress } from "@/api/http";

/* ---------- Path helpers ---------- */

export function buildProjectDeletePath(projectId: string): string {
  return `/api/project/${projectId}`;
}

/* ---------- Project CRUD ---------- */

export function listProjects(limit = 20): Promise<ApiResponse> {
  return get(`/api/project/list?limit=${limit}`);
}

export function getProject(projectId: string): Promise<ApiResponse> {
  return get(`/api/project/${projectId}`);
}

export function getProjectGraph(projectId: string): Promise<ApiResponse> {
  return get(`/api/project/${projectId}/graph`);
}

export function deleteProject(projectId: string): Promise<ApiResponse> {
  return del(buildProjectDeletePath(projectId));
}

/* ---------- Graph building ---------- */

export function buildGraph(
  projectId: string,
  graphName = "Novel Story Graph",
): Promise<ApiResponse> {
  return post("/api/project/build-graph", {
    project_id: projectId,
    graph_name: graphName,
  });
}

/* ---------- Task tracking ---------- */

export function getTask(taskId: string): Promise<ApiResponse> {
  return get(`/api/project/task/${taskId}`);
}

export function getStepTrace(taskId: string, stepId: string): Promise<ApiResponse> {
  return get(`/api/project/task/${taskId}/steps/${stepId}/trace`);
}

export function cancelTask(taskId: string): Promise<ApiResponse> {
  return post(`/api/project/task/${taskId}/cancel`);
}

/* ---------- Seed upload ---------- */

export interface UploadStorySeedParams {
  projectName: string;
  analysisGoal: string;
  additionalContext?: string;
  segmentTokenLimit?: number;
  files?: File[];
  onProgress?: (progress: UploadProgress) => void;
  onRequest?: (xhr: XMLHttpRequest) => void;
}

export function uploadStorySeed({
  projectName,
  analysisGoal,
  additionalContext,
  segmentTokenLimit,
  files = [],
  onProgress,
  onRequest,
}: UploadStorySeedParams): Promise<ApiResponse> {
  const formData = new FormData();
  formData.append("project_name", projectName);
  formData.append("analysis_goal", analysisGoal);
  formData.append("additional_context", additionalContext || "");
  if (segmentTokenLimit) {
    formData.append("segment_token_limit", String(segmentTokenLimit));
  }
  for (const file of files) {
    formData.append("files", file);
  }
  return uploadForm("/api/project/seed/extract", formData, { onProgress, onRequest });
}
