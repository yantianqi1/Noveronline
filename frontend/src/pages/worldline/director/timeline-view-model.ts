/**
 * Director timeline view model: builds timeline entries from canon events.
 *
 * Ported from: src-vue/views/worldline/director/directorTimelineViewModel.js
 */

import { parseSummaryArtifacts } from "../event-summary-parser";

/* ================================================================
 * Types
 * ================================================================ */

export interface TimelineVariableEffect {
  name: string;
  description: string;
}

export interface TimelineActionEffect {
  actor: string;
  action: string;
  intent: string;
  target: string;
}

export interface TimelineRelationChange {
  source: string;
  target: string;
  label: string;
  note: string;
}

export interface TimelineStateChange {
  entityName: string;
  status: string;
  reason: string;
}

export interface TimelineActorSummary {
  name: string;
  initial: string;
  actionCount: number;
}

export interface TimelineEntry {
  eventId: string;
  step: number;
  stepLabel: string;
  title: string;
  summary: string;
  drivers: string[];
  variableEffects: TimelineVariableEffect[];
  actionEffects: TimelineActionEffect[];
  relationChanges: TimelineRelationChange[];
  stateChanges: TimelineStateChange[];
  actorSummaries: TimelineActorSummary[];
  isLatest: boolean;
}

export interface TimelineData {
  emptyMessage: string;
  items: TimelineEntry[];
}

/* ================================================================
 * Helpers
 * ================================================================ */

const EMPTY_MESSAGE = "当前世界还没有新的世界变化，推进后会在这里连续记录局势改写。";

function buildStepLabel(step: number): string {
  return `STEP ${step}`;
}

function formatRelationChange(change: string | undefined): string {
  return change || "关系变化";
}

function formatAgentStatus(status: string | undefined): string {
  return status || "未知";
}

/* ================================================================
 * Event normalization
 * ================================================================ */

interface InternalEvent {
  title: string;
  summary: string;
  drivingEntities: string[];
  actionEffects: TimelineActionEffect[];
  variableEffects: TimelineVariableEffect[];
  relationChanges: TimelineRelationChange[];
  stateChanges: TimelineStateChange[];
  eventId: string;
  step: number;
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
    eventId: (event?.event_id as string) || "",
    step: (event?.step as number) ?? 0,
  };
}

function mapVariableEffects(items: Array<Record<string, unknown>> = []): TimelineVariableEffect[] {
  return items.map((i) => ({
    name: (i.name as string) || "变量",
    description: (i.description as string) || (i.name as string) || "未提供变量描述",
  }));
}

function mapActionEffects(items: Array<Record<string, unknown>> = []): TimelineActionEffect[] {
  return items.map((i) => ({
    actor: (i.actor as string) || (i.name as string) || "未知 agent",
    action: (i.action as string) || (i.description as string) || "未提供动作",
    intent: (i.intent as string) || "",
    target: (i.target as string) || "",
  }));
}

function mapRelationChanges(items: Array<Record<string, unknown>> | undefined): TimelineRelationChange[] {
  return (items || []).map((i) => ({
    source: (i.source as string) || "",
    target: (i.target as string) || "",
    label: formatRelationChange(i.change as string),
    note: (i.note as string) || "关系结构正在重排",
  }));
}

function mapStateChanges(items: Array<Record<string, unknown>> | undefined): TimelineStateChange[] {
  return (items || []).map((i) => ({
    entityName:
      (i.entity_name as string) || (i.entity as string) || (i.name as string) || "未知对象",
    status: formatAgentStatus(i.status as string),
    reason: (i.reason as string) || "局势推进",
  }));
}

/* ================================================================
 * Main builder
 * ================================================================ */

export function buildTimelineEntries(
  timeline: Array<Record<string, unknown>> = [],
): TimelineData {
  const canonEvents = timeline.filter(
    (e) => ((e.status as string) || "canon") === "canon",
  );
  if (!canonEvents.length) {
    return { emptyMessage: EMPTY_MESSAGE, items: [] };
  }

  const reversed = [...canonEvents].reverse();
  return {
    emptyMessage: "",
    items: reversed.map((event, index) =>
      buildEntry(normalizeEvent(event), index === 0),
    ),
  };
}

function buildEntry(event: InternalEvent, isLatest: boolean): TimelineEntry {
  const actions = event.actionEffects;
  const variables = event.variableEffects;
  const parts: string[] = [];
  if (variables.length) parts.push(`变量 ${variables.length} 条已触发`);
  if (actions.length) parts.push(`agent 动作 ${actions.length} 条已落地`);
  const digest = parts.length
    ? parts.join("，")
    : event.summary || "等待新的剧情推进。";

  const actorSet = new Map<string, TimelineActorSummary>();
  for (const a of actions) {
    const prev = actorSet.get(a.actor);
    actorSet.set(a.actor, {
      name: a.actor,
      initial: a.actor.charAt(0),
      actionCount: (prev?.actionCount || 0) + 1,
    });
  }
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
