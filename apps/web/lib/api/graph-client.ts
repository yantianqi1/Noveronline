import type {
  GraphClusters,
  GraphEdgeDetail,
  GraphEvidence,
  GraphNodeDetail,
  GraphSnapshot,
  GraphView,
} from "@/lib/api/graph-types";
import { readSelectionFor } from "@/lib/api/writer-client";

/**
 * Browser-side client for the Story Graph (故事图谱) workbench. All calls go to
 * same-origin BFF routes; the browser supplies the tenant via X-Tenant-Id (from
 * the shelf selection). Reads need no CSRF token; the one mutation
 * (startGraphBuild) is cookie-authenticated and so carries the X-CSRF-Token
 * header like the other workbench mutations.
 */

export class GraphError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "GraphError";
  }
}

/** The active project/tenant selection, but only when it matches this project. */
export function readGraphSelection(projectId: string) {
  return readSelectionFor(projectId);
}

async function readError(response: Response): Promise<GraphError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // non-JSON body — keep the generic message
  }
  return new GraphError(message, code, response.status);
}

async function getJson<T>(path: string, tenantId: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json", "X-Tenant-Id": tenantId },
    cache: "no-store",
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

async function postJson<T>(path: string, tenantId: string, csrfToken: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

/** Latest ready/building/failed snapshot for the project's graph. */
export function fetchGraphSnapshot(projectId: string, tenantId: string): Promise<GraphSnapshot> {
  return getJson<GraphSnapshot>(`/api/projects/${projectId}/story-graph/current`, tenantId);
}

/**
 * A ranked viewport of nodes (optionally the induced edges between them).
 * `types` filters by backend node_type; an empty array returns every type.
 */
export function fetchGraphView(
  projectId: string,
  tenantId: string,
  options: { viewId?: string; types?: string[]; limit?: number; includeEdges?: boolean } = {},
): Promise<GraphView> {
  const params = new URLSearchParams();
  if (options.types && options.types.length > 0) params.set("types", options.types.join(","));
  if (options.limit && options.limit > 0) params.set("limit", String(options.limit));
  if (options.includeEdges) params.set("include_edges", "true");
  const viewId = options.viewId ?? "world";
  const query = params.toString();
  return getJson<GraphView>(
    `/api/projects/${projectId}/story-graph/views/${encodeURIComponent(viewId)}${query ? `?${query}` : ""}`,
    tenantId,
  );
}

/** One node's public detail (node + aliases + labels). */
export function fetchGraphNode(
  projectId: string,
  tenantId: string,
  nodeId: string,
): Promise<GraphNodeDetail> {
  return getJson<GraphNodeDetail>(
    `/api/projects/${projectId}/story-graph/nodes/${encodeURIComponent(nodeId)}`,
    tenantId,
  );
}

/** One edge's public detail. */
export function fetchGraphEdge(
  projectId: string,
  tenantId: string,
  edgeId: string,
): Promise<GraphEdgeDetail> {
  return getJson<GraphEdgeDetail>(
    `/api/projects/${projectId}/story-graph/edges/${encodeURIComponent(edgeId)}`,
    tenantId,
  );
}

/** Public evidence source metadata for a node (no snippet on the public read). */
export function fetchNodeEvidence(
  projectId: string,
  tenantId: string,
  nodeId: string,
  limit = 24,
): Promise<GraphEvidence> {
  return getJson<GraphEvidence>(
    `/api/projects/${projectId}/story-graph/nodes/${encodeURIComponent(nodeId)}/evidence?limit=${limit}`,
    tenantId,
  );
}

/** Cluster summaries used to group / label neighbourhoods of the graph. */
export function fetchGraphClusters(
  projectId: string,
  tenantId: string,
  limit = 60,
): Promise<GraphClusters> {
  return getJson<GraphClusters>(
    `/api/projects/${projectId}/story-graph/clusters?limit=${limit}`,
    tenantId,
  );
}

export type GraphBuildStart = {
  run_id: string;
  project_id: string;
  workflow_type: string;
  status: string;
};

/**
 * Queue a full story-graph build. The build is asynchronous: the server returns
 * `{status: "queued"}` immediately and the snapshot's status moves
 * building → ready/failed, which the workbench polls via fetchGraphSnapshot.
 */
export function startGraphBuild(
  projectId: string,
  tenantId: string,
  csrfToken: string,
): Promise<GraphBuildStart> {
  return postJson<GraphBuildStart>(
    `/api/projects/${projectId}/story-graph/builds`,
    tenantId,
    csrfToken,
    { mode: "full" },
  );
}

/** Snapshot absent (GraphEmpty state) vs. present. `status` is null when absent. */
export function snapshotStatusOrNull(snapshot: GraphSnapshot | null): string | null {
  return snapshot ? snapshot.status : null;
}
