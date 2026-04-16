/**
 * Worldline API client — session lifecycle, agents, timeline, events, dialogue.
 */

import { get, post } from "@/api/http";
import type { ApiResponse } from "@/api/http";

/* ---------- Query builder ---------- */

export interface WorldlineQueryFilters {
  branchId?: string;
  branch_id?: string;
  agentId?: string;
  agent_id?: string;
  status?: string;
  limit?: number;
  message?: string;
}

function buildWorldlineQuery(filters: WorldlineQueryFilters = {}): string {
  const params = new URLSearchParams();
  const resolvedBranchId = filters.branchId || filters.branch_id;
  const resolvedAgentId = filters.agentId || filters.agent_id;
  if (resolvedBranchId) {
    params.set("branch_id", resolvedBranchId);
  }
  if (resolvedAgentId) {
    params.set("agent_id", resolvedAgentId);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (typeof filters.limit === "number" && Number.isFinite(filters.limit)) {
    params.set("limit", String(filters.limit));
  }
  if (filters.message) {
    params.set("message", filters.message);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return suffix;
}

/* ---------- Session lifecycle ---------- */

export function createWorldlineSession(payload: unknown): Promise<ApiResponse> {
  return post("/api/worldline/session/create", payload);
}

export function prepareWorldlineSession(payload: unknown): Promise<ApiResponse> {
  return post("/api/worldline/session/prepare", payload);
}

export function getPreparedWorldlineSession(
  prepareId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/prepare/${prepareId}${suffix}`);
}

export function getPreparedWorldlineAgents(
  prepareId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/prepare/${prepareId}/agents${suffix}`);
}

export function startPreparedWorldlineSession(
  prepareId: string,
  payload: unknown = {},
): Promise<ApiResponse> {
  return post(`/api/worldline/session/prepare/${prepareId}/start`, payload);
}

export function startWorldlineAutoEvolve(payload: {
  session_id: string;
  branch_ids?: unknown;
  [key: string]: unknown;
}): Promise<ApiResponse> {
  const { session_id: sessionId, branch_ids, ...singleWorldPayload } = payload;
  void branch_ids;
  return post(`/api/worldline/session/${sessionId}/auto-evolve`, singleWorldPayload);
}

/* ---------- Session list ---------- */

export function buildWorldlineSessionListPath(
  { projectId }: { projectId?: string } = {},
): string {
  const params = new URLSearchParams();
  if (projectId) {
    params.set("project_id", projectId);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/worldline/session/list${suffix}`;
}

export function getWorldlineSession(sessionId: string): Promise<ApiResponse> {
  return get(`/api/worldline/session/${sessionId}`);
}

export function listWorldlineSessions(
  filters: { projectId?: string } = {},
): Promise<ApiResponse> {
  return get(buildWorldlineSessionListPath(filters));
}

/* ---------- Session actions ---------- */

export function advanceWorldlineStep(payload: {
  session_id: string;
  [key: string]: unknown;
}): Promise<ApiResponse> {
  const { session_id: sessionId, ...rest } = payload;
  return post(`/api/worldline/session/${sessionId}/step`, rest);
}

export function injectWorldlineVariable(payload: {
  session_id: string;
  [key: string]: unknown;
}): Promise<ApiResponse> {
  const { session_id: sessionId, ...rest } = payload;
  return post(`/api/worldline/session/${sessionId}/inject-variable`, rest);
}

export function issueAgentAction(payload: {
  session_id: string;
  [key: string]: unknown;
}): Promise<ApiResponse> {
  const { session_id: sessionId, ...rest } = payload;
  return post(`/api/worldline/session/${sessionId}/agent-action`, rest);
}

/* ---------- Timeline ---------- */

export function getWorldlineTimeline(
  sessionId: string,
  branchId?: string,
): Promise<ApiResponse> {
  void branchId;
  return get(`/api/worldline/session/${sessionId}/timeline`);
}

/* ---------- Agents ---------- */

export function getWorldlineAgents(
  sessionId: string,
  branchId?: string,
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery({ branchId });
  return get(`/api/worldline/session/${sessionId}/agents${suffix}`);
}

export function getWorldlineAgentDetail(
  sessionId: string,
  agentId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(
    `/api/worldline/session/${sessionId}/agents/${encodeURIComponent(agentId)}${suffix}`,
  );
}

export function getWorldlineAgentHistory(
  sessionId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-history${suffix}`);
}

export function getWorldlineAgentMemory(
  sessionId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-memory${suffix}`);
}

export function getWorldlineAgentMemoryContext(
  sessionId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-memory-context${suffix}`);
}

export function getWorldlineAgentActions(
  sessionId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-actions${suffix}`);
}

export function getWorldlineAgentDialogues(
  sessionId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-dialogues${suffix}`);
}

export function getWorldlineRelationHistory(
  sessionId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/relation-history${suffix}`);
}

/* ---------- Agent dialogue ---------- */

export function chatWithWorldlineAgent(payload: {
  session_id: string;
  [key: string]: unknown;
}): Promise<ApiResponse> {
  const { session_id: sessionId, ...rest } = payload;
  return post(`/api/worldline/session/${sessionId}/agent-dialogue`, rest);
}

/* ---------- Plot inspiration ---------- */

export function generatePlotInspiration(payload: unknown): Promise<ApiResponse> {
  return post("/api/novel/plot/inspiration", payload);
}

/* ---------- Candidate / Canon event management ---------- */

export function adoptWorldlineEvents(payload: {
  session_id: string;
  [key: string]: unknown;
}): Promise<ApiResponse> {
  const { session_id: sessionId, ...rest } = payload;
  return post(`/api/worldline/session/${sessionId}/events/adopt`, rest);
}

export function editWorldlineEvent(payload: {
  session_id: string;
  event_id: string;
  [key: string]: unknown;
}): Promise<ApiResponse> {
  const { session_id: sessionId, event_id: eventId, ...rest } = payload;
  return post(
    `/api/worldline/session/${sessionId}/events/${encodeURIComponent(eventId)}/edit`,
    rest,
  );
}

export function getWorldlineCandidateEvents(
  sessionId: string,
  filters: WorldlineQueryFilters = {},
): Promise<ApiResponse> {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/events/candidates${suffix}`);
}

export function getWorldlineCanonEvents(sessionId: string): Promise<ApiResponse> {
  return get(`/api/worldline/session/${sessionId}/events/canon`);
}
