export interface Project {
  id: string;
  name: string;
  status: string;  // CREATED | SEED_PROCESSING | ONTOLOGY_GENERATED | GRAPH_BUILDING | GRAPH_COMPLETED | FAILED
  analysis_goal: string;
  created_at: string;
  updated_at: string;
  file_count?: number;
  total_size?: number;
  seed_task_id?: string | null;
  graph_build_task_id?: string | null;
}

export interface Task {
  task_id: string;
  task_type: string;
  status: string;  // processing | completed | failed | cancelled
  progress: number;
  result?: unknown;
  error?: string;
  started_at?: string;
  completed_at?: string;
  metrics?: Record<string, unknown>;
  timeline?: TaskTimelineEntry[];
  active_stage?: string;
  llm_activity?: LlmCallInfo[];
}

export interface TaskTimelineEntry {
  stage: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  detail?: string;
}

export interface LlmCallInfo {
  module: string;
  channel_key: string;
  model_id: string;
  started_at: string;
  status: string;
}

export interface StepTrace {
  step_id: string;
  content: string;
  timestamp: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta?: Record<string, unknown>;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  importance_tier?: string;
  labels?: string[];
  aliases?: string[];
  properties?: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
  properties?: Record<string, unknown>;
}
