/**
 * Spotlight view model: builds per-actor action cards and spotlight data
 * from the latest event and world state.
 *
 * Ported from: src-vue/views/worldline/director/directorSpotlightViewModel.js
 */

import { parseSummaryArtifacts } from "../event-summary-parser";

/* ================================================================
 * Types
 * ================================================================ */

export interface SpotlightActionEffect {
  actor: string;
  action: string;
  intent: string;
  target: string;
}

export interface SpotlightVariableEffect {
  name: string;
  description: string;
}

export interface SpotlightRelationChange {
  source: string;
  target: string;
  label: string;
  note: string;
}

export interface SpotlightStateChange {
  entityName: string;
  status: string;
  reason: string;
}

export interface ActorActionCard {
  name: string;
  initial: string;
  role: string;
  status: string;
  drive: string;
  isDriver: boolean;
  actions: SpotlightActionEffect[];
  relationChanges: SpotlightRelationChange[];
  stateChange: SpotlightStateChange | null;
}

export interface SpotlightNarrativeEvent {
  title: string;
  summary: string;
  digest: string;
  drivers: string[];
  variableEffects: SpotlightVariableEffect[];
  actionEffects: SpotlightActionEffect[];
  relationChanges: SpotlightRelationChange[];
}

export interface SpotlightPendingSummary {
  variableCount: number;
  actionCount: number;
}

export interface SpotlightData {
  worldId: string;
  title: string;
  currentStep: number;
  stepLabel: string;
  status: string;
  statusLabel: string;
  progress: number;
  coreChange: string;
  latestEvent: SpotlightNarrativeEvent;
  drivers: string[];
  pending: SpotlightPendingSummary;
  actorActionCards: ActorActionCard[];
  isEmpty: boolean;
}

/* ================================================================
 * Helpers
 * ================================================================ */

const EMPTY_MESSAGE = "当前世界还没有新的推进记录，继续演化后会在这里生成导演台摘要。";

function buildStepLabel(step: number): string {
  return `STEP ${step}`;
}

function formatAgentStatus(status: string | undefined): string {
  return status || "未知";
}

function formatRoleText(role: string | undefined): string {
  return role || "";
}

function formatBranchStatus(status: string): string {
  const map: Record<string, string> = {
    running: "推演中",
    paused: "暂停",
    idle: "待命",
    completed: "已完成",
    pending: "准备中",
  };
  return map[status] || status || "未知";
}

/* ================================================================
 * Event normalization
 * ================================================================ */

interface InternalEvent {
  title: string;
  summary: string;
  drivingEntities: string[];
  actionEffects: SpotlightActionEffect[];
  variableEffects: SpotlightVariableEffect[];
  relationChanges: SpotlightRelationChange[];
  stateChanges: SpotlightStateChange[];
}

function normalizeEvent(
  event: Record<string, unknown> | null | undefined,
): InternalEvent {
  const parsed = parseSummaryArtifacts(
    (event?.summary as string) || (event?.description as string) || "",
  );
  const rawActions = event?.action_effects as Array<Record<string, unknown>> | undefined;
  const rawVars = event?.variable_effects as Array<Record<string, unknown>> | undefined;
  const actionEffects = mapActionEffects(rawActions?.length ? rawActions : (parsed.actionEffects as unknown as Array<Record<string, unknown>>));
  const variableEffects = mapVariableEffects(rawVars?.length ? rawVars : (parsed.variableEffects as unknown as Array<Record<string, unknown>>));
  return {
    title: (event?.title as string) || "",
    summary: (event?.summary as string) || (event?.description as string) || "",
    drivingEntities: [
      ...new Set([
        ...((event?.driving_entities as string[]) || []),
        ...actionEffects.map((i) => i.actor),
      ]),
    ],
    actionEffects,
    variableEffects,
    relationChanges: mapRelationChanges(event?.relation_changes as Array<Record<string, unknown>>),
    stateChanges: mapStateChanges(event?.state_changes as Array<Record<string, unknown>>),
  };
}

function resolveLatestEvent(
  taskEvent: Record<string, unknown> | null | undefined,
  timelineEvent: Record<string, unknown> | null | undefined,
): InternalEvent {
  const a = normalizeEvent(taskEvent);
  const b = normalizeEvent(timelineEvent);
  return {
    title: a.title || b.title || "暂无新事件",
    summary: a.summary || b.summary || "等待新的剧情推进。",
    drivingEntities: a.drivingEntities.length ? a.drivingEntities : b.drivingEntities,
    variableEffects: a.variableEffects.length ? a.variableEffects : b.variableEffects,
    actionEffects: a.actionEffects.length ? a.actionEffects : b.actionEffects,
    relationChanges: a.relationChanges.length ? a.relationChanges : b.relationChanges,
    stateChanges: a.stateChanges.length ? a.stateChanges : b.stateChanges,
  };
}

function resolveTimelineLatest(
  timeline: Array<Record<string, unknown>>,
): Record<string, unknown> | null {
  return timeline.length ? timeline[timeline.length - 1]! : null;
}

function resolveWorldStatus(
  currentWorld: Record<string, unknown> | null,
  taskSnapshot: Record<string, unknown> | null,
): string {
  if (taskSnapshot?.task_id) return (taskSnapshot.status as string) || "pending";
  if (((currentWorld?.current_step as number) ?? 0) > 0) return "paused";
  return "idle";
}

function resolveProgress(
  taskSnapshot: Record<string, unknown> | null,
  status: string,
): number {
  if (taskSnapshot?.task_id && Number.isFinite(taskSnapshot?.progress)) {
    return taskSnapshot.progress as number;
  }
  return status === "completed" || status === "paused" ? 100 : 0;
}

function buildDigest(primary: InternalEvent, fallback: InternalEvent): string {
  const actions = primary.actionEffects.length ? primary.actionEffects : fallback.actionEffects;
  const variables = primary.variableEffects.length ? primary.variableEffects : fallback.variableEffects;
  const parts: string[] = [];
  if (variables.length) parts.push(`变量 ${variables.length} 条已触发`);
  if (actions.length) parts.push(`agent 动作 ${actions.length} 条已落地`);
  return parts.length ? parts.join("，") : (primary.summary || fallback.summary || "等待新的剧情推进。");
}

function buildPendingSummary(
  currentWorld: Record<string, unknown> | null,
): SpotlightPendingSummary {
  const pv = currentWorld?.pending_variables;
  const pa = currentWorld?.pending_actions;
  return {
    variableCount:
      (currentWorld?.pending_variable_count as number) ??
      (Array.isArray(pv) ? pv.length : (currentWorld?.pending_variables as number) ?? 0),
    actionCount:
      (currentWorld?.pending_action_count as number) ??
      (Array.isArray(pa) ? pa.length : (currentWorld?.pending_actions as number) ?? 0),
  };
}

function mapStateCollection(states: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(states)) return states;
  return Object.entries((states as Record<string, unknown>) || {}).map(
    ([name, state]) => ({ name, ...((state as Record<string, unknown>) || {}) }),
  );
}

function mapVariableEffects(items: Array<Record<string, unknown>> = []): SpotlightVariableEffect[] {
  return items.map((i) => ({
    name: (i.name as string) || "变量",
    description: (i.description as string) || (i.name as string) || "未提供变量描述",
  }));
}

function mapActionEffects(items: Array<Record<string, unknown>> = []): SpotlightActionEffect[] {
  return items.map((i) => ({
    actor: (i.actor as string) || (i.name as string) || "未知 agent",
    action: (i.action as string) || (i.description as string) || "未提供动作",
    intent: (i.intent as string) || "",
    target: (i.target as string) || "",
  }));
}

function mapRelationChanges(items: Array<Record<string, unknown>> | undefined): SpotlightRelationChange[] {
  return (items || []).map((i) => ({
    source: (i.source as string) || "",
    target: (i.target as string) || "",
    label: (i.change as string) || "关系变化",
    note: (i.note as string) || "",
  }));
}

function mapStateChanges(items: Array<Record<string, unknown>> | undefined): SpotlightStateChange[] {
  return (items || []).map((i) => ({
    entityName: (i.entity_name as string) || (i.entity as string) || (i.name as string) || "",
    status: formatAgentStatus(i.status as string),
    reason: (i.reason as string) || "",
  }));
}

/* ================================================================
 * Actor action card builder
 * ================================================================ */

function makeEmptyCard(
  name: string,
  actorStates: Array<Record<string, unknown>>,
  driverSet: Set<string>,
): ActorActionCard {
  const state = actorStates.find((s) => s.name === name);
  return {
    name,
    initial: name.charAt(0),
    role: state ? formatRoleText(state.role as string) : "",
    status: state ? formatAgentStatus(state.status as string) : "",
    drive: (state?.drive as string) || "",
    isDriver: driverSet.has(name),
    actions: [],
    relationChanges: [],
    stateChange: null,
  };
}

function buildActorActionCards(
  latestEvent: InternalEvent,
  actorStates: Array<Record<string, unknown>> = [],
  drivers: string[] = [],
): ActorActionCard[] {
  const driverSet = new Set(drivers);
  const cardMap = new Map<string, ActorActionCard>();

  for (const action of latestEvent.actionEffects) {
    if (!cardMap.has(action.actor)) {
      cardMap.set(action.actor, makeEmptyCard(action.actor, actorStates, driverSet));
    }
    cardMap.get(action.actor)!.actions.push(action);
  }

  for (const name of drivers) {
    if (!cardMap.has(name)) {
      cardMap.set(name, makeEmptyCard(name, actorStates, driverSet));
    }
  }

  for (const rel of latestEvent.relationChanges) {
    const owner = rel.source || rel.target;
    if (owner && cardMap.has(owner)) {
      cardMap.get(owner)!.relationChanges.push(rel);
    } else if (owner) {
      cardMap.set(owner, makeEmptyCard(owner, actorStates, driverSet));
      cardMap.get(owner)!.relationChanges.push(rel);
    }
  }

  for (const sc of latestEvent.stateChanges) {
    if (sc.entityName && cardMap.has(sc.entityName)) {
      cardMap.get(sc.entityName)!.stateChange = sc;
    }
  }

  const cards = [...cardMap.values()];
  cards.sort((a, b) => {
    if (a.isDriver !== b.isDriver) return a.isDriver ? -1 : 1;
    return b.actions.length - a.actions.length;
  });
  return cards;
}

/* ================================================================
 * Main builder
 * ================================================================ */

export function buildSpotlightData(opts: {
  currentWorld?: Record<string, unknown> | null;
  taskSnapshot?: Record<string, unknown> | null;
  timeline?: Array<Record<string, unknown>>;
}): SpotlightData {
  const { currentWorld = null, taskSnapshot = null, timeline = [] } = opts;
  const latestEvent = resolveLatestEvent(
    taskSnapshot?.latest_event as Record<string, unknown>,
    resolveTimelineLatest(timeline),
  );
  const status = resolveWorldStatus(currentWorld, taskSnapshot);
  const currentStep = (currentWorld?.current_step as number) ?? 0;
  const pending = buildPendingSummary(currentWorld);

  const actorActionCards = buildActorActionCards(
    latestEvent,
    mapStateCollection(currentWorld?.actor_states),
    latestEvent.drivingEntities,
  );

  return {
    worldId: (currentWorld?.branch_id as string) || "main",
    title: (currentWorld?.title as string) || "当前世界",
    currentStep,
    stepLabel: buildStepLabel(currentStep),
    status,
    statusLabel: formatBranchStatus(status === "processing" ? "running" : status),
    progress: resolveProgress(taskSnapshot, status),
    coreChange: (currentWorld?.core_change as string) || EMPTY_MESSAGE,
    latestEvent: {
      title: latestEvent.title,
      summary: latestEvent.summary,
      digest: buildDigest(latestEvent, {
        title: "",
        summary: "",
        drivingEntities: [],
        actionEffects: [],
        variableEffects: [],
        relationChanges: [],
        stateChanges: [],
      }),
      drivers: latestEvent.drivingEntities,
      variableEffects: latestEvent.variableEffects,
      actionEffects: latestEvent.actionEffects,
      relationChanges: latestEvent.relationChanges,
    },
    drivers: latestEvent.drivingEntities,
    pending,
    actorActionCards,
    isEmpty: !currentWorld && !timeline.length,
  };
}
