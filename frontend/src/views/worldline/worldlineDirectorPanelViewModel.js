import {
  buildStepLabel,
  formatAgentStatus,
  formatBranchStatus,
  formatRelationChange,
  formatRoleText,
} from "../../utils/chineseDisplay.js";
import { parseSummaryArtifacts } from "./worldlineEventSummaryParser.js";

const WORLD_SHIFT_EMPTY_MESSAGE = "当前世界还没有新的世界变化，推进后会在这里连续记录局势改写。";
const DIRECTOR_EMPTY_MESSAGE = "当前世界还没有新的推进记录，继续演化后会在这里生成导演台摘要。";

export function buildWorldlineCurrentWorldSummary({
  currentWorld = null,
  taskSnapshot = null,
  timeline = [],
} = {}) {
  const latestEvent = resolveLatestEvent(taskSnapshot?.latest_event, resolveTimelineLatestEvent(timeline));
  const pending = buildPendingSummary(currentWorld);
  const status = resolveWorldStatus(currentWorld, taskSnapshot);
  const currentStep = currentWorld?.current_step ?? 0;
  return {
    worldId: currentWorld?.branch_id || "main",
    title: currentWorld?.title || "当前世界",
    currentStep,
    stepLabel: buildStepLabel(currentStep),
    status,
    statusLabel: formatBranchStatus(status === "processing" ? "running" : status),
    progress: resolveProgress(taskSnapshot, status),
    latestEventTitle: latestEvent.title,
    latestEventSummary: latestEvent.summary,
    drivers: latestEvent.drivingEntities,
    pendingCount: pending.variableCount + pending.actionCount,
  };
}

export function buildWorldlineFocusNarrative({
  currentWorld = null,
  taskSnapshot = null,
  timeline = [],
} = {}) {
  const latestEvent = resolveLatestEvent(taskSnapshot?.latest_event, resolveTimelineLatestEvent(timeline));
  const status = resolveWorldStatus(currentWorld, taskSnapshot);
  const drivers = latestEvent.drivingEntities;
  return {
    worldId: currentWorld?.branch_id || "main",
    title: currentWorld?.title || "当前世界",
    currentStep: currentWorld?.current_step ?? 0,
    stepLabel: buildStepLabel(currentWorld?.current_step ?? 0),
    status,
    statusLabel: formatBranchStatus(status === "processing" ? "running" : status),
    coreChange: currentWorld?.core_change || DIRECTOR_EMPTY_MESSAGE,
    latestEvent: buildNarrativeEvent(latestEvent),
    dispatchActors: buildDispatchActors(mapStateCollection(currentWorld?.actor_states), drivers),
    relationChanges: buildRelationChanges(latestEvent, currentWorld),
    pending: buildPendingSummary(currentWorld),
    worldForces: buildWorldForces(mapStateCollection(currentWorld?.organization_states)),
    emptyMessage: currentWorld ? "" : DIRECTOR_EMPTY_MESSAGE,
  };
}

export function buildWorldlineWorldShiftFeed(timeline = []) {
  // Only show canon events in the shift feed; candidate events are reviewed separately.
  const canonEvents = timeline.filter((e) => (e.status || "canon") === "canon");
  if (!canonEvents.length) {
    return { emptyMessage: WORLD_SHIFT_EMPTY_MESSAGE, items: [] };
  }
  return {
    emptyMessage: "",
    items: [...canonEvents].reverse().map((event) => buildShiftItem(normalizeEvent(event))),
  };
}

function mapStateCollection(states) {
  if (Array.isArray(states)) {
    return states;
  }
  return Object.entries(states || {}).map(([name, state]) => ({ name, ...(state || {}) }));
}

function resolveLatestEvent(taskEvent, timelineEvent) {
  const taskSnapshot = normalizeEvent(taskEvent);
  const timelineSnapshot = normalizeEvent(timelineEvent);
  return {
    title: taskSnapshot.title || timelineSnapshot.title || "暂无新事件",
    summary: taskSnapshot.summary || timelineSnapshot.summary || "等待新的剧情推进。",
    digest: buildEventDigest(taskSnapshot, timelineSnapshot),
    drivingEntities: resolveDrivers(taskSnapshot, timelineSnapshot),
    variableEffects: resolveList(taskSnapshot.variableEffects, timelineSnapshot.variableEffects),
    actionEffects: resolveList(taskSnapshot.actionEffects, timelineSnapshot.actionEffects),
    relationChanges: resolveList(taskSnapshot.relationChanges, timelineSnapshot.relationChanges),
  };
}

function normalizeEvent(event) {
  const parsed = parseSummaryArtifacts(event?.summary || event?.description || "");
  const actionEffects = mapActionEffects(event?.action_effects?.length ? event.action_effects : parsed.actionEffects);
  const variableEffects = mapVariableEffects(event?.variable_effects?.length ? event.variable_effects : parsed.variableEffects);
  return {
    title: event?.title || "",
    summary: event?.summary || event?.description || "",
    drivingEntities: [...new Set([...(event?.driving_entities || []), ...actionEffects.map((item) => item.actor)])],
    actionEffects,
    variableEffects,
    relationChanges: mapRelationChanges(event?.relation_changes),
    stateChanges: mapStateChanges(event?.state_changes),
    eventId: event?.event_id || "",
    step: event?.step ?? 0,
  };
}

function resolveDrivers(taskSnapshot, timelineSnapshot) {
  if (taskSnapshot.drivingEntities.length) {
    return taskSnapshot.drivingEntities;
  }
  return timelineSnapshot.drivingEntities;
}

function resolveTimelineLatestEvent(timeline = []) {
  return timeline.length ? timeline[timeline.length - 1] : null;
}

function resolveWorldStatus(currentWorld, taskSnapshot) {
  if (taskSnapshot?.task_id) {
    return taskSnapshot.status || "pending";
  }
  if ((currentWorld?.current_step ?? 0) > 0) {
    return "paused";
  }
  return "idle";
}

function resolveProgress(taskSnapshot, status) {
  if (taskSnapshot?.task_id && Number.isFinite(taskSnapshot?.progress)) {
    return taskSnapshot.progress;
  }
  return status === "completed" || status === "paused" ? 100 : 0;
}

function buildNarrativeEvent(event) {
  return {
    title: event.title,
    summary: event.summary,
    digest: event.digest,
    drivers: event.drivingEntities,
    variableEffects: event.variableEffects,
    actionEffects: event.actionEffects,
  };
}

function buildDispatchActors(actorStates = [], drivers = []) {
  const cards = actorStates.map((item) => ({
    name: item.name,
    role: formatRoleText(item.role),
    status: formatAgentStatus(item.status),
    drive: item.drive || "继续围绕当前目标行动",
    isDriver: drivers.includes(item.name),
  }));
  const knownNames = new Set(cards.map((item) => item.name));
  const synthesized = drivers
    .filter((name) => !knownNames.has(name))
    .map((name) => ({
      name,
      role: "驱动者",
      status: "活跃",
      drive: "直接推动当前回合演化",
      isDriver: true,
    }));
  return [...cards, ...synthesized].sort((left, right) => Number(right.isDriver) - Number(left.isDriver));
}

function buildRelationChanges(latestEvent, currentWorld) {
  if (latestEvent.relationChanges.length) {
    return latestEvent.relationChanges;
  }
  const relationStates = Array.isArray(currentWorld?.relationship_states) ? currentWorld.relationship_states : [];
  return mapRelationChanges(relationStates.slice(-3));
}

function buildPendingSummary(currentWorld) {
  const pendingVariables = currentWorld?.pending_variables;
  const pendingActions = currentWorld?.pending_actions;
  return {
    variableCount: currentWorld?.pending_variable_count
      ?? (Array.isArray(pendingVariables) ? pendingVariables.length : currentWorld?.pending_variables ?? 0),
    variableNames: Array.isArray(pendingVariables)
      ? pendingVariables.slice(0, 4).map((item) => item.name || item.description || "变量")
      : [],
    actionCount: currentWorld?.pending_action_count
      ?? (Array.isArray(pendingActions) ? pendingActions.length : currentWorld?.pending_actions ?? 0),
    actionLabels: Array.isArray(pendingActions)
      ? pendingActions.slice(0, 4).map((item) => `${item.actor}:${item.action}`)
      : [],
  };
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
  return items.map((item) => ({
    name: item.name || "变量",
    description: item.description || item.name || "未提供变量描述",
  }));
}

function mapActionEffects(items = []) {
  return items.map((item) => ({
    actor: item.actor || item.name || "未知 agent",
    action: item.action || item.description || "未提供动作",
    intent: item.intent || "",
    target: item.target || "",
  }));
}

function mapRelationChanges(items = []) {
  return items.map((item) => ({
    source: item.source || "",
    target: item.target || "",
    label: formatRelationChange(item.change),
    note: item.note || "关系结构正在重排",
  }));
}

function mapStateChanges(items = []) {
  return items.map((item) => ({
    entityName: item.entity_name || item.entity || item.name || "未知对象",
    status: formatAgentStatus(item.status),
    reason: item.reason || "局势推进",
    action: item.action || "",
    influence: item.influence ?? null,
  }));
}

function resolveList(primary = [], fallback = []) {
  return primary.length ? primary : fallback;
}

function buildEventDigest(primary, fallback) {
  const actions = resolveList(primary.actionEffects, fallback.actionEffects);
  const variables = resolveList(primary.variableEffects, fallback.variableEffects);
  const segments = [];
  if (variables.length) {
    segments.push(`变量 ${variables.length} 条已触发`);
  }
  if (actions.length) {
    segments.push(`agent 动作 ${actions.length} 条已落地`);
  }
  return segments.length ? segments.join("，") : (primary.summary || fallback.summary || "等待新的剧情推进。");
}

function buildShiftItem(event) {
  return {
    eventId: event.eventId,
    step: event.step,
    stepLabel: buildStepLabel(event.step),
    title: event.title || "事件",
    summary: buildEventDigest(event, {}),
    drivers: event.drivingEntities,
    variableEffects: event.variableEffects,
    actionEffects: event.actionEffects,
    relationChanges: event.relationChanges,
    stateChanges: event.stateChanges,
  };
}
