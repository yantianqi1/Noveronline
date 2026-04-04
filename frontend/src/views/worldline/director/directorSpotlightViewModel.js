import {
  buildStepLabel,
  formatAgentStatus,
  formatBranchStatus,
  formatRelationChange,
  formatRoleText,
} from "../../../utils/chineseDisplay.js";
import { parseSummaryArtifacts } from "../worldlineEventSummaryParser.js";

const EMPTY_MESSAGE = "当前世界还没有新的推进记录，继续演化后会在这里生成导演台摘要。";

export function buildSpotlightData({
  currentWorld = null,
  taskSnapshot = null,
  timeline = [],
} = {}) {
  const latestEvent = resolveLatestEvent(taskSnapshot?.latest_event, resolveTimelineLatest(timeline));
  const status = resolveWorldStatus(currentWorld, taskSnapshot);
  const currentStep = currentWorld?.current_step ?? 0;
  const pending = buildPendingSummary(currentWorld);

  const actorActionCards = buildActorActionCards(
    latestEvent,
    mapStateCollection(currentWorld?.actor_states),
    latestEvent.drivingEntities,
  );

  return {
    worldId: currentWorld?.branch_id || "main",
    title: currentWorld?.title || "当前世界",
    currentStep,
    stepLabel: buildStepLabel(currentStep),
    status,
    statusLabel: formatBranchStatus(status === "processing" ? "running" : status),
    progress: resolveProgress(taskSnapshot, status),
    coreChange: currentWorld?.core_change || EMPTY_MESSAGE,
    latestEvent: buildNarrativeEvent(latestEvent),
    drivers: latestEvent.drivingEntities,
    pending,
    actorActionCards,
    isEmpty: !currentWorld && !timeline.length,
  };
}

/* ── internals ─────────────────────────────────────────────── */

function resolveTimelineLatest(timeline) {
  return timeline.length ? timeline[timeline.length - 1] : null;
}

function resolveLatestEvent(taskEvent, timelineEvent) {
  const a = normalizeEvent(taskEvent);
  const b = normalizeEvent(timelineEvent);
  return {
    title: a.title || b.title || "暂无新事件",
    summary: a.summary || b.summary || "等待新的剧情推进。",
    digest: buildDigest(a, b),
    drivingEntities: a.drivingEntities.length ? a.drivingEntities : b.drivingEntities,
    variableEffects: a.variableEffects.length ? a.variableEffects : b.variableEffects,
    actionEffects: a.actionEffects.length ? a.actionEffects : b.actionEffects,
    relationChanges: a.relationChanges.length ? a.relationChanges : b.relationChanges,
    stateChanges: a.stateChanges.length ? a.stateChanges : b.stateChanges,
  };
}

function normalizeEvent(event) {
  const parsed = parseSummaryArtifacts(event?.summary || event?.description || "");
  const actionEffects = mapActionEffects(event?.action_effects?.length ? event.action_effects : parsed.actionEffects);
  const variableEffects = mapVariableEffects(event?.variable_effects?.length ? event.variable_effects : parsed.variableEffects);
  return {
    title: event?.title || "",
    summary: event?.summary || event?.description || "",
    drivingEntities: [...new Set([...(event?.driving_entities || []), ...actionEffects.map((i) => i.actor)])],
    actionEffects,
    variableEffects,
    relationChanges: mapRelationChanges(event?.relation_changes),
    stateChanges: mapStateChanges(event?.state_changes),
  };
}

function buildNarrativeEvent(event) {
  return {
    title: event.title,
    summary: event.summary,
    digest: event.digest,
    drivers: event.drivingEntities,
    variableEffects: event.variableEffects,
    actionEffects: event.actionEffects,
    relationChanges: event.relationChanges,
  };
}

function buildDigest(primary, fallback) {
  const actions = primary.actionEffects.length ? primary.actionEffects : fallback.actionEffects;
  const variables = primary.variableEffects.length ? primary.variableEffects : fallback.variableEffects;
  const parts = [];
  if (variables.length) parts.push(`变量 ${variables.length} 条已触发`);
  if (actions.length) parts.push(`agent 动作 ${actions.length} 条已落地`);
  return parts.length ? parts.join("，") : (primary.summary || fallback.summary || "等待新的剧情推进。");
}

function resolveWorldStatus(currentWorld, taskSnapshot) {
  if (taskSnapshot?.task_id) return taskSnapshot.status || "pending";
  if ((currentWorld?.current_step ?? 0) > 0) return "paused";
  return "idle";
}

function resolveProgress(taskSnapshot, status) {
  if (taskSnapshot?.task_id && Number.isFinite(taskSnapshot?.progress)) return taskSnapshot.progress;
  return status === "completed" || status === "paused" ? 100 : 0;
}

function buildPendingSummary(currentWorld) {
  const pv = currentWorld?.pending_variables;
  const pa = currentWorld?.pending_actions;
  return {
    variableCount: currentWorld?.pending_variable_count
      ?? (Array.isArray(pv) ? pv.length : currentWorld?.pending_variables ?? 0),
    variableNames: Array.isArray(pv)
      ? pv.slice(0, 4).map((i) => i.name || i.description || "变量")
      : [],
    actionCount: currentWorld?.pending_action_count
      ?? (Array.isArray(pa) ? pa.length : currentWorld?.pending_actions ?? 0),
    actionLabels: Array.isArray(pa)
      ? pa.slice(0, 4).map((i) => `${i.actor}:${i.action}`)
      : [],
  };
}

function mapStateCollection(states) {
  if (Array.isArray(states)) return states;
  return Object.entries(states || {}).map(([name, state]) => ({ name, ...(state || {}) }));
}

function buildDispatchActors(actorStates = [], drivers = []) {
  const cards = actorStates.map((item) => ({
    name: item.name,
    role: formatRoleText(item.role),
    status: formatAgentStatus(item.status),
    drive: item.drive || "继续围绕当前目标行动",
    isDriver: drivers.includes(item.name),
  }));
  const knownNames = new Set(cards.map((i) => i.name));
  const synthesized = drivers
    .filter((name) => !knownNames.has(name))
    .map((name) => ({ name, role: "驱动者", status: "活跃", drive: "直接推动当前回合演化", isDriver: true }));
  return [...cards, ...synthesized].sort((a, b) => Number(b.isDriver) - Number(a.isDriver));
}

function buildWorldForces(organizations = []) {
  return organizations.map((item) => ({
    name: item.name,
    role: formatRoleText(item.role),
    status: formatAgentStatus(item.status),
    summary: item.drive || item.tension || "仍在调整阵营位置",
  }));
}

function mapVariableEffects(items = []) {
  return items.map((i) => ({ name: i.name || "变量", description: i.description || i.name || "未提供变量描述" }));
}

function mapActionEffects(items = []) {
  return items.map((i) => ({
    actor: i.actor || i.name || "未知 agent",
    action: i.action || i.description || "未提供动作",
    intent: i.intent || "",
    target: i.target || "",
  }));
}

function mapRelationChanges(items = []) {
  return (items || []).map((i) => ({
    source: i.source || "",
    target: i.target || "",
    label: formatRelationChange(i.change),
    note: i.note || "",
  }));
}

function mapStateChanges(items = []) {
  return (items || []).map((i) => ({
    entityName: i.entity_name || i.entity || i.name || "",
    status: formatAgentStatus(i.status),
    reason: i.reason || "",
  }));
}

/**
 * Cross-reference all effect arrays by actor name to produce per-actor cards.
 */
function buildActorActionCards(latestEvent, actorStates = [], drivers = []) {
  const driverSet = new Set(drivers);
  const cardMap = new Map();

  // Seed from actors who took actions
  for (const action of latestEvent.actionEffects) {
    if (!cardMap.has(action.actor)) {
      cardMap.set(action.actor, makeEmptyCard(action.actor, actorStates, driverSet));
    }
    cardMap.get(action.actor).actions.push(action);
  }

  // Add drivers who may not have explicit actions
  for (const name of drivers) {
    if (!cardMap.has(name)) {
      cardMap.set(name, makeEmptyCard(name, actorStates, driverSet));
    }
  }

  // Assign relation changes to the source actor
  for (const rel of latestEvent.relationChanges) {
    const owner = rel.source || rel.target;
    if (owner && cardMap.has(owner)) {
      cardMap.get(owner).relationChanges.push(rel);
    } else if (owner) {
      cardMap.set(owner, makeEmptyCard(owner, actorStates, driverSet));
      cardMap.get(owner).relationChanges.push(rel);
    }
  }

  // Assign state changes
  for (const sc of latestEvent.stateChanges) {
    if (sc.entityName && cardMap.has(sc.entityName)) {
      cardMap.get(sc.entityName).stateChange = sc;
    }
  }

  // Sort: drivers first, then by action count
  const cards = [...cardMap.values()];
  cards.sort((a, b) => {
    if (a.isDriver !== b.isDriver) return a.isDriver ? -1 : 1;
    return b.actions.length - a.actions.length;
  });
  return cards;
}

function makeEmptyCard(name, actorStates, driverSet) {
  const state = actorStates.find((s) => s.name === name);
  return {
    name,
    initial: name.charAt(0),
    role: state ? formatRoleText(state.role) : "",
    status: state ? formatAgentStatus(state.status) : "",
    drive: state?.drive || "",
    isDriver: driverSet.has(name),
    actions: [],
    relationChanges: [],
    stateChange: null,
  };
}
