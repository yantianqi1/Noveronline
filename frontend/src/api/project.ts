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

/**
 * 触发对仍标记为 retry_needed 的段落的手动重读。
 * 后端返回一个新的 task_id,前端用 getTask 轮询其进度。
 */
export function retryFailedSegments(projectId: string): Promise<ApiResponse> {
  return post(`/api/project/seed/retry-failed-segments/${projectId}`);
}

/**
 * 使用已上传的文件重新运行种子管线（从头来过）。
 * 当上一次分析卡死或中断后，用户希望完整重试时调用。
 */
export function rerunSeedPipeline(projectId: string): Promise<ApiResponse> {
  return post(`/api/project/seed/rerun/${projectId}`);
}

/**
 * 手动触发"重新打通数据"：再跑一次档案同步 / 图谱构建 / 全局索引重建。
 * 后端返回一个新的 task_id,前端用 getTask 轮询其进度。
 */
export function relinkProjectData(projectId: string): Promise<ApiResponse> {
  return post(`/api/project/${projectId}/relink-data`);
}

/* ---------- Graph LLM bond / plot-thread generation ---------- */

export interface GraphBondGenerateRequest {
  node_uuids: string[];
  generate_bonds?: boolean;
  generate_threads?: boolean;
}

export interface GeneratedBond {
  source_name: string;
  target_name: string;
  relation_type: string;
  description: string;
  trust_level: number | null;
  power_dynamic: string;
  history: string;
  conflict_trigger: string;
  persisted: boolean;
  relation_id: string | null;
  skip_reason: string;
}

export interface GeneratedPlotThread {
  thread_key: string;
  detail: string;
  status: string;
  involved_names: string[];
  persisted: boolean;
  thread_id: string | null;
  linked_entity_ids: string[];
  skip_reason: string;
}

export interface GraphBondGenerateResponse {
  bonds: GeneratedBond[];
  plot_threads: GeneratedPlotThread[];
  unmapped_names: string[];
  selected_nodes: Array<{
    uuid: string;
    name: string;
    labels: string[];
    entity_id: string | null;
  }>;
}

export function generateGraphBond(
  projectId: string,
  payload: GraphBondGenerateRequest,
): Promise<ApiResponse<GraphBondGenerateResponse>> {
  return post(`/api/project/${projectId}/graph/generate-bond`, payload);
}
