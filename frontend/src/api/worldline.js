import { get, post } from "./http";

export function createWorldlineSession(payload) {
  return post("/api/worldline/session/create", payload);
}

export function buildWorldlineSessionListPath({ projectId } = {}) {
  const params = new URLSearchParams();
  if (projectId) {
    params.set("project_id", projectId);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/worldline/session/list${suffix}`;
}

export function getWorldlineSession(sessionId) {
  return get(`/api/worldline/session/${sessionId}`);
}

export function listWorldlineSessions(filters = {}) {
  return get(buildWorldlineSessionListPath(filters));
}

export function advanceWorldlineStep({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/step`, payload);
}

export function injectWorldlineVariable({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/inject-variable`, payload);
}

export function issueAgentAction({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/agent-action`, payload);
}

export function listWorldlineBranches(sessionId) {
  return get(`/api/worldline/session/${sessionId}/branches`);
}

export function getWorldlineComparison(sessionId, branchIds = []) {
  const params = new URLSearchParams();
  if (branchIds.length) {
    params.set("branch_ids", branchIds.join(","));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return get(`/api/worldline/session/${sessionId}/comparison${suffix}`);
}

export function getWorldlineTimeline(sessionId, branchId) {
  return get(`/api/worldline/session/${sessionId}/branch/${branchId}/timeline`);
}

export function getWorldlineAgents(sessionId, branchId) {
  const suffix = buildWorldlineQuery({ branchId });
  return get(`/api/worldline/session/${sessionId}/agents${suffix}`);
}

export function getWorldlineAgentHistory(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-history${suffix}`);
}

export function getWorldlineAgentActions(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-actions${suffix}`);
}

export function getWorldlineAgentDialogues(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-dialogues${suffix}`);
}

export function getWorldlineRelationHistory(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/relation-history${suffix}`);
}

function buildWorldlineQuery({
  branchId,
  branch_id: rawBranchId,
  agentId,
  agent_id: rawAgentId,
  status,
  limit,
} = {}) {
  const params = new URLSearchParams();
  const resolvedBranchId = branchId || rawBranchId;
  const resolvedAgentId = agentId || rawAgentId;
  if (resolvedBranchId) {
    params.set("branch_id", resolvedBranchId);
  }
  if (resolvedAgentId) {
    params.set("agent_id", resolvedAgentId);
  }
  if (status) {
    params.set("status", status);
  }
  if (typeof limit === "number" && Number.isFinite(limit)) {
    params.set("limit", String(limit));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return suffix;
}

export function chatWithWorldlineAgent({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/agent-dialogue`, payload);
}

export function generatePlotInspiration(payload) {
  return post("/api/novel/plot/inspiration", payload);
}
