import type { WorldlineEvent, WorldlineTimelineEvent } from "@/lib/api/worldline-types";

/**
 * Pure derivation logic for the Worldline 方案A workbench (主线＋裁决队列).
 * Everything here is side-effect free and import-only-types, so node:test can
 * import this file directly (Node's type stripping erases the `import type`).
 * Statuses are the backend literals: candidate / canon / rejected.
 */

// ── 步骤印章 ────────────────────────────────────────────────────────────────

const STEP_NUMERALS = ["〇", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖", "拾"];

/** Brush-numeral seal for a domain step; orchestration markers (step 0) get a dot. */
export function stepNumeral(step: number): string {
  if (step > 0 && step < STEP_NUMERALS.length) return STEP_NUMERALS[step];
  if (step > 0) return String(step);
  return "·";
}

// ── 状态芯片三态 ────────────────────────────────────────────────────────────

export type WorldlineChipState = "idle" | "running" | "judging";

export const WORLDLINE_CHIP_LABELS: Record<WorldlineChipState, string> = {
  idle: "待推进",
  running: "推演中",
  judging: "待裁决",
};

/**
 * The one status chip on the 状态行: 待裁决 while any candidate awaits the
 * author (they must be settled before the world moves on), else 推演中 while a
 * step is queued/running (or the local poll is still open), else 待推进.
 */
export function worldlineChipState(input: {
  sessionStatus: string;
  candidateCount: number;
  evolving?: boolean;
}): WorldlineChipState {
  if (input.candidateCount > 0) return "judging";
  if (input.evolving || input.sessionStatus === "running" || input.sessionStatus === "queued") {
    return "running";
  }
  return "idle";
}

// ── 候选 / 正史分区 ─────────────────────────────────────────────────────────

/**
 * Split a session's events into the two lanes the workbench renders. Rejected
 * events belong to neither — the backend persisted the author's 「暂不采纳」,
 * so they must never resurface in the queue or the timeline.
 */
export function partitionWorldlineEvents(events: WorldlineEvent[]): {
  candidates: WorldlineEvent[];
  canon: WorldlineEvent[];
} {
  const candidates: WorldlineEvent[] = [];
  const canon: WorldlineEvent[] = [];
  for (const event of events) {
    if (event.status === "candidate") candidates.push(event);
    else if (event.status === "canon") canon.push(event);
  }
  return { candidates, canon };
}

// ── 计数与待定夺步号 ────────────────────────────────────────────────────────

/** Masthead counts line, e.g. "6 段正史 · 3 条待定夺". */
export function formatWorldlineCounts(canonCount: number, pendingCount: number): string {
  return `${canonCount} 段正史 · ${pendingCount} 条待定夺`;
}

/** The step the director is drafting candidates for — always current + 1. */
export function pendingStepFor(currentStep: number): number {
  return currentStep + 1;
}

// ── 整备阶段阶梯 ────────────────────────────────────────────────────────────

export const GOAL_START_STAGES: { key: string; label: string; hint: string }[] = [
  { key: "casting", label: "选角", hint: "拆解目标，从资产库挑选演员与素材" },
  { key: "preparing", label: "整备演员", hint: "为每位演员生成档案与就位状态" },
  { key: "starting", label: "建立会话", hint: "把整备好的世界线装订成一次推演" },
];

/** queued → casting → preparing → starting → ready, mapped onto the 3-stage ladder. */
export function goalStartStageIndex(status: string): number {
  switch (status) {
    case "casting":
      return 0;
    case "preparing":
      return 1;
    case "starting":
      return 2;
    case "ready":
      return GOAL_START_STAGES.length;
    default:
      return 0; // queued — the cast stage is about to start
  }
}

// ── 状态变化视图 ────────────────────────────────────────────────────────────

/** Orchestration bookkeeping keys that never belong in the author-facing rows. */
const STATE_CHANGE_HIDDEN_KEYS = new Set(["summary", "model_id", "mode", "source_step_index", "source_workflow_type"]);

export type StateChangeView = {
  /** The director's one-line 状态变化 summary, when it wrote one. */
  summary: string;
  /** Remaining key/value changes, stringified for the detail rows. */
  entries: { key: string; value: string }[];
};

/** Shape one event's state_changes into what the expanded card / candidate shows. */
export function stateChangeView(stateChanges: Record<string, unknown> | null | undefined): StateChangeView {
  const changes = stateChanges ?? {};
  const summary = typeof changes.summary === "string" ? changes.summary.trim() : "";
  const entries = Object.entries(changes)
    .filter(([key]) => !STATE_CHANGE_HIDDEN_KEYS.has(key))
    .map(([key, value]) => ({ key, value: String(value) }));
  return { summary, entries };
}

// ── 涉及角色名解析 ──────────────────────────────────────────────────────────

/**
 * Names an event actually involves: resolve involved_agent_ids against the
 * roster first (ids or display names); the director's slugs that map to nothing
 * fall back to roster names literally present in the event text. Never invents
 * a name — an unresolvable id is dropped, not echoed raw.
 */
export function involvedNamesForEvent(
  event: Pick<WorldlineEvent, "title" | "summary" | "involved_agent_ids">,
  roster: { id: string; name: string }[],
): string[] {
  const byKey = new Map<string, string>();
  for (const member of roster) {
    if (member.id) byKey.set(member.id, member.name);
    if (member.name) byKey.set(member.name, member.name);
  }
  const resolved = (event.involved_agent_ids ?? [])
    .map((raw) => byKey.get(raw.trim()) ?? "")
    .filter(Boolean);
  if (resolved.length > 0) return [...new Set(resolved)];
  const text = `${event.title} ${event.summary}`;
  return roster.filter((member) => member.name && text.includes(member.name)).map((member) => member.name);
}

// ── 时间线行 → 正史卡片事件 ─────────────────────────────────────────────────

/**
 * Rejection ledger rows (payload kind `event_rejection`, event_type
 * `worldline.event.rejected`) are backend bookkeeping: the rejected candidate's
 * title mirrors onto the row via the event_ref_id join, but the 正史阅读列 must
 * never read it — a 暂不采纳/自动未采纳 candidate leaves the queue and stays out
 * of the timeline. The record itself stays in the backend ledger untouched.
 */
export function isRejectionTimelineRow(t: Pick<WorldlineTimelineEvent, "kind" | "event_type">): boolean {
  if (t.kind === "event_rejection") return true;
  return /reject/.test(t.event_type ?? "");
}

/**
 * Map one timeline row onto an event card. Adoption rows surface the adopted
 * domain event (title/summary/kind/confidence/agents/state changes, joined via
 * the backend's event_ref_id) instead of the orchestration bookkeeping text.
 * The card's step is the DOMAIN step of the referenced event — the timeline's
 * own `sequence` counts orchestration rows (an adoption bumps it without
 * stepping the world), so it never feeds "第 N 步".
 */
export function timelineEventToWorldlineEvent(
  t: WorldlineTimelineEvent,
  projectId: string,
  canonById: ReadonlyMap<string, WorldlineEvent>,
): WorldlineEvent {
  const isAdoption = t.kind === "event_adoption" || Boolean(t.event_ref_id);
  const adopted = isAdoption && t.event_ref_id?.trim() ? canonById.get(t.event_ref_id) : undefined;
  return {
    event_id: t.event_ref_id?.trim() ? t.event_ref_id : t.event_id,
    session_id: t.session_id,
    project_id: projectId,
    step: adopted?.step ?? 0,
    title: adopted?.title ?? (isAdoption && t.adopted_title?.trim() ? t.adopted_title : t.title),
    summary: adopted?.summary ?? (isAdoption && t.adopted_summary?.trim() ? t.adopted_summary : t.summary),
    kind: adopted?.kind ?? t.kind,
    status: t.status,
    lifecycle: t.lifecycle,
    event_type: t.event_type,
    confidence: adopted?.confidence ?? "",
    involved_agent_ids: adopted?.involved_agent_ids ?? [],
    state_changes: adopted?.state_changes ?? {},
    source_run_id: t.run_id,
    created_by: "",
    created_at: t.created_at,
    updated_at: t.created_at,
  };
}

export function timelineEventsToWorldlineEvents(
  timeline: WorldlineTimelineEvent[],
  projectId: string,
  canonEvents: WorldlineEvent[],
): WorldlineEvent[] {
  const canonById = new Map(canonEvents.map((e) => [e.event_id, e] as const));
  // 阅读列只读正史与采纳落位:拒绝台账行在映射前剔除(数据仍在后端)。
  return timeline
    .filter((t) => !isRejectionTimelineRow(t))
    .map((t) => timelineEventToWorldlineEvent(t, projectId, canonById));
}
