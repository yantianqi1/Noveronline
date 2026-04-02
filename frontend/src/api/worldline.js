import { get, post } from "./http.js";

export function createWorldlineSession(payload) {
  return post("/api/worldline/session/create", payload);
}

export function prepareWorldlineSession(payload) {
  return post("/api/worldline/session/prepare", payload);
}

export function getPreparedWorldlineSession(prepareId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/prepare/${prepareId}${suffix}`);
}

export function getPreparedWorldlineAgents(prepareId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/prepare/${prepareId}/agents${suffix}`);
}

export function startPreparedWorldlineSession(prepareId, payload = {}) {
  return post(`/api/worldline/session/prepare/${prepareId}/start`, payload);
}

export function startWorldlineAutoEvolve({ session_id: sessionId, ...payload }) {
  const { branch_ids, ...singleWorldPayload } = payload;
  void branch_ids;
  return post(`/api/worldline/session/${sessionId}/auto-evolve`, singleWorldPayload);
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

export function getWorldlineTimeline(sessionId, branchId) {
  void branchId;
  return get(`/api/worldline/session/${sessionId}/timeline`);
}

export function getWorldlineAgents(sessionId, branchId) {
  const suffix = buildWorldlineQuery({ branchId });
  return get(`/api/worldline/session/${sessionId}/agents${suffix}`);
}

export function getWorldlineAgentDetail(sessionId, agentId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agents/${encodeURIComponent(agentId)}${suffix}`);
}

export function getWorldlineAgentHistory(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-history${suffix}`);
}

export function getWorldlineAgentMemory(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-memory${suffix}`);
}

export function getWorldlineAgentMemoryContext(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-memory-context${suffix}`);
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
  message,
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
  if (message) {
    params.set("message", message);
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

/* --- Candidate / Canon event management --- */

export function adoptWorldlineEvents({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/events/adopt`, payload);
}

export function editWorldlineEvent({ session_id: sessionId, event_id: eventId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/events/${encodeURIComponent(eventId)}/edit`, payload);
}

export function getWorldlineCandidateEvents(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/events/candidates${suffix}`);
}

export function getWorldlineCanonEvents(sessionId) {
  return get(`/api/worldline/session/${sessionId}/events/canon`);
}
