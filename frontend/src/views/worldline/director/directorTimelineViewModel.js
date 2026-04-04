import { buildStepLabel, formatRelationChange, formatAgentStatus } from "../../../utils/chineseDisplay.js";
import { parseSummaryArtifacts } from "../worldlineEventSummaryParser.js";

const EMPTY_MESSAGE = "当前世界还没有新的世界变化，推进后会在这里连续记录局势改写。";

export function buildTimelineEntries(timeline = []) {
  const canonEvents = timeline.filter((e) => (e.status || "canon") === "canon");
  if (!canonEvents.length) {
    return { emptyMessage: EMPTY_MESSAGE, items: [] };
  }

  const reversed = [...canonEvents].reverse();
  return {
    emptyMessage: "",
    items: reversed.map((event, index) => buildEntry(normalizeEvent(event), index === 0)),
  };
}

function buildEntry(event, isLatest) {
  const actions = event.actionEffects;
  const variables = event.variableEffects;
  const parts = [];
  if (variables.length) parts.push(`变量 ${variables.length} 条已触发`);
  if (actions.length) parts.push(`agent 动作 ${actions.length} 条已落地`);
  const digest = parts.length ? parts.join("，") : (event.summary || "等待新的剧情推进。");

  // Build compact actor summaries for collapsed timeline display.
  const actorSet = new Map();
  for (const a of actions) {
    const prev = actorSet.get(a.actor);
    actorSet.set(a.actor, { name: a.actor, initial: a.actor.charAt(0), actionCount: (prev?.actionCount || 0) + 1 });
  }
  // Include drivers who may not have explicit actions
  for (const d of event.drivingEntities) {
    if (!actorSet.has(d)) {
      actorSet.set(d, { name: d, initial: d.charAt(0), actionCount: 0 });
    }
  }

  return {
    eventId: event.eventId,
    step: event.step,
    stepLabel: buildStepLabel(event.step),
    title: event.title || "事件",
    summary: digest,
    drivers: event.drivingEntities,
    variableEffects: event.variableEffects,
    actionEffects: event.actionEffects,
    relationChanges: event.relationChanges,
    stateChanges: event.stateChanges,
    actorSummaries: [...actorSet.values()],
    isLatest,
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
    eventId: event?.event_id || "",
    step: event?.step ?? 0,
  };
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
    note: i.note || "关系结构正在重排",
  }));
}

function mapStateChanges(items = []) {
  return (items || []).map((i) => ({
    entityName: i.entity_name || i.entity || i.name || "未知对象",
    status: formatAgentStatus(i.status),
    reason: i.reason || "局势推进",
  }));
}
