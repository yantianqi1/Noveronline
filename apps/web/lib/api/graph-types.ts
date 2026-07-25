/**
 * Wire types mirroring the Go control plane's storygraph package
 * (apps/api/internal/storygraph/storygraph.go). Field names are snake_case as
 * they appear on the wire. The public read side is sanitized server-side:
 * prompt/body/content/raw text/snippet/credential keys never reach the browser,
 * and evidence snippets are only present when the caller passed include_full
 * through the permission gate.
 */

export type GraphSnapshot = {
  graph_id: string;
  project_id: string;
  version: number;
  status: string;
  build_run_id: string;
  source_version_hash: string;
  node_count: number;
  edge_count: number;
  created_at: string;
  updated_at: string;
};

export type GraphNode = {
  node_id: string;
  graph_id: string;
  project_id: string;
  canonical_entity_id: string;
  node_type: string;
  title: string;
  summary: string;
  lifecycle: string;
  importance: number;
  cluster_id: string;
  attributes: Record<string, unknown>;
  evidence_count: number;
  created_at: string;
  updated_at: string;
};

export type GraphEdge = {
  edge_id: string;
  graph_id: string;
  project_id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  label: string;
  summary: string;
  weight: number;
  lifecycle: string;
  attributes: Record<string, unknown>;
  evidence_count: number;
  created_at: string;
  updated_at: string;
};

export type GraphReadStrategy = {
  mode: string;
  offset: number;
  applied_limit: number;
  max_page_size: number;
  returned_count: number;
  has_more: boolean;
  next_offset?: number;
  ordering: string;
  edge_scope?: string;
};

export type GraphView = {
  view_id: string;
  graph_id: string;
  project_id: string;
  limit: number;
  include_edges: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  read_strategy: GraphReadStrategy;
};

export type GraphNodeDetail = {
  node: GraphNode;
  aliases: string[];
  labels: string[];
};

export type GraphEdgeDetail = {
  edge: GraphEdge;
};

export type GraphEvidenceRecord = {
  evidence_id: string;
  graph_id: string;
  project_id: string;
  owner_type: string;
  owner_id: string;
  source_type: string;
  source_id: string;
  chapter_id: string;
  segment_id: string;
  snippet?: string;
  confidence: number;
  created_at: string;
  updated_at: string;
};

export type GraphEvidence = {
  graph_id: string;
  project_id: string;
  owner_type: string;
  owner_id: string;
  limit: number;
  items: GraphEvidenceRecord[];
};

export type GraphCluster = {
  cluster_id: string;
  graph_id: string;
  project_id: string;
  cluster_key: string;
  title: string;
  summary: string;
  node_count: number;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type GraphClusters = {
  graph_id: string;
  project_id: string;
  limit: number;
  items: GraphCluster[];
  read_strategy: GraphReadStrategy;
};
