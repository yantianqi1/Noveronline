import type { WriterEvent } from "@/lib/api/writer-types";

/**
 * Reduce a run's raw event stream into a presentable run-state model. This is
 * the transport→domain boundary: components render this, never raw events.
 * Pure + unit-tested, so the event-contract quirks (100-event pages, token
 * chunks, terminal events) live in exactly one place.
 */

export type RunPhase =
  | "queued"
  | "orchestrating" // retrieval planning + tool loop
  | "composing" // streaming prose
  | "completed"
  | "failed"
  | "cancelled";

/** One legible step of the run — a retrieval/tool action, author-facing. */
export type RunStep = {
  id: string;
  /** Author-legible label (no UUIDs/tool ids/raw codes). */
  label: string;
  status: "running" | "completed" | "error";
};

/** A piece of canon/seed/material the agent recalled into the writing brief. */
export type RunCitation = {
  assetId: string;
  title: string;
  lifecycle: string;
  channel: string;
};

/** A canon contradiction the consistency checker found in the draft. */
export type ConsistencyViolation = {
  canonLabel: string;
  conflict: string;
  severity: "minor" | "major";
};

export type WriterRunState = {
  phase: RunPhase;
  /** Human-legible current-step label, author-facing (no UUID/tool ids). */
  statusLine: string;
  /** Number of tool calls made so far (retrieval evidence gathering). */
  toolCount: number;
  /** The run's tool/retrieval steps, in order, for the expandable detail. */
  steps: RunStep[];
  /** Canon/seed/material recalled via semantic search, deduped by asset. */
  citations: RunCitation[];
  /** True when semantic recall degraded to keyword-only (embeddings unavailable). */
  citationsDegraded: boolean;
  /** Post-generation consistency violations (canon contradictions), if any. */
  consistencyViolations: ConsistencyViolation[];
  /** Concatenated candidate prose from writer.token events. */
  candidateText: string;
  /** Set when the run saved a draft (writer.draft.saved). */
  draftId: string | null;
  /** Author-facing failure/cancel reason, when terminal and not completed. */
  terminalMessage: string | null;
  isTerminal: boolean;
};

const TERMINAL: ReadonlySet<RunPhase> = new Set(["completed", "failed", "cancelled"]);

export function reduceWriterRun(events: WriterEvent[]): WriterRunState {
  let phase: RunPhase = "queued";
  let toolCount = 0;
  let candidateText = "";
  let draftId: string | null = null;
  let terminalMessage: string | null = null;
  let sawStarted = false;
  const steps: RunStep[] = [];
  const stepIndexByCallId = new Map<string, number>();
  const citations: RunCitation[] = [];
  const seenCitationIds = new Set<string>();
  let citationsDegraded = false;
  const consistencyViolations: ConsistencyViolation[] = [];

  // Process in stream order.
  const ordered = [...events].sort((a, b) => a.sequence - b.sequence);
  for (const event of ordered) {
    const type = event.event_type;
    const payload = (event.payload ?? {}) as Record<string, unknown>;

    switch (type) {
      case "writer.run.started":
        sawStarted = true;
        if (!TERMINAL.has(phase)) phase = "orchestrating";
        break;
      case "writer.tool.started": {
        toolCount += 1;
        const callId = toolCallId(payload, toolCount);
        stepIndexByCallId.set(callId, steps.length);
        steps.push({ id: callId, label: toolLabel(payload, toolCount), status: "running" });
        if (!TERMINAL.has(phase)) phase = "orchestrating";
        break;
      }
      case "writer.tool.completed":
      case "writer.tool.failed": {
        const callId = toolCallId(payload, 0);
        const index = stepIndexByCallId.get(callId);
        if (index !== undefined) {
          steps[index] = {
            ...steps[index],
            status: type === "writer.tool.failed" ? "error" : "completed",
          };
        }
        if (type === "writer.tool.completed" && payload.tool_name === "search_assets") {
          const result = (payload.result ?? {}) as Record<string, unknown>;
          if (result.degraded === true) citationsDegraded = true;
          for (const item of Array.isArray(result.items) ? result.items : []) {
            const c = item as Record<string, unknown>;
            const assetId = typeof c.asset_id === "string" ? c.asset_id : "";
            if (!assetId || seenCitationIds.has(assetId)) continue;
            seenCitationIds.add(assetId);
            citations.push({
              assetId,
              title: typeof c.title === "string" && c.title.trim() ? c.title : "未命名设定",
              lifecycle: typeof c.lifecycle === "string" ? c.lifecycle : "",
              channel: typeof c.channel === "string" ? c.channel : "search_assets",
            });
          }
        }
        // Constant-injection (always_on) canon rides the fused recall. Collect it
        // as a citation so the rail can mark it as 常驻 (always present), distinct
        // from relevance-recalled assets.
        if (type === "writer.tool.completed" && payload.tool_name === "fuse_recall") {
          const result = (payload.result ?? {}) as Record<string, unknown>;
          for (const item of Array.isArray(result.items) ? result.items : []) {
            const c = item as Record<string, unknown>;
            if (c.channel !== "always_on") continue;
            const assetId = typeof c.asset_id === "string" ? c.asset_id : "";
            if (!assetId || seenCitationIds.has(assetId)) continue;
            seenCitationIds.add(assetId);
            citations.push({
              assetId,
              title: typeof c.title === "string" && c.title.trim() ? c.title : "未命名设定",
              lifecycle: "常驻",
              channel: "always_on",
            });
          }
        }
        break;
      }
      case "writer.token":
        candidateText += typeof payload.token === "string" ? payload.token : "";
        if (!TERMINAL.has(phase)) phase = "composing";
        break;
      case "writer.draft.saved":
        if (typeof payload.draft_id === "string") draftId = payload.draft_id;
        break;
      case "writer.consistency.violations": {
        const items = Array.isArray(payload.violations) ? payload.violations : [];
        for (const item of items) {
          const v = item as Record<string, unknown>;
          const label = typeof v.canon_label === "string" ? v.canon_label : "";
          const conflict = typeof v.conflict === "string" ? v.conflict : "";
          if (!label || !conflict) continue;
          consistencyViolations.push({
            canonLabel: label,
            conflict,
            severity: v.severity === "major" ? "major" : "minor",
          });
        }
        break;
      }
      case "writer.run.completed":
        phase = "completed";
        break;
      case "writer.run.failed":
        phase = "failed";
        terminalMessage = authorMessage(payload, "这次起草没写成");
        break;
      case "writer.run.cancelled":
        phase = "cancelled";
        terminalMessage = "已停下";
        break;
      default:
        break;
    }
  }

  return {
    phase,
    statusLine: statusLineFor(phase, toolCount, candidateText, sawStarted, terminalMessage),
    toolCount,
    steps,
    citations,
    citationsDegraded,
    consistencyViolations,
    candidateText,
    draftId,
    terminalMessage,
    isTerminal: TERMINAL.has(phase),
  };
}

/** Pull a stable tool-call id, falling back to a positional key. */
function toolCallId(payload: Record<string, unknown>, fallback: number): string {
  const raw = payload.tool_call_id ?? payload.call_id ?? payload.id;
  return typeof raw === "string" && raw.length > 0 ? raw : `call-${fallback}`;
}

/**
 * Author-legible labels for the orchestrator's retrieval tools. The backend
 * emits snake_case tool names; the rail shows what the agent is actually
 * reading, in calm novel-domain language. Unknown tools fall back to a generic
 * retrieval label so no raw identifier ever leaks.
 */
const TOOL_LABELS: Record<string, string> = {
  query_project_context: "查阅全书设定",
  query_chapter_scene: "查阅章节与场景",
  query_assets: "查阅勾选资产",
  search_assets: "语义召回设定",
  search_manuscript: "召回前文呼应",
  fuse_recall: "融合多路召回",
  query_world_rules: "查阅世界规则",
  query_character_profile: "查阅角色档案",
  query_graph_neighbors: "查阅故事图谱",
  query_worldline_paths: "查阅世界线走向",
  query_manuscript_context: "查阅现有手稿",
};

/**
 * Label a tool step in author language. Maps the orchestrator's known
 * retrieval tools to calm labels; anything else becomes a generic retrieval
 * step. Never surfaces raw ids, codes, or stack fragments.
 */
function toolLabel(payload: Record<string, unknown>, ordinal: number): string {
  const raw = payload.tool_name ?? payload.name ?? payload.tool;
  if (typeof raw === "string" && raw.trim().length > 0) {
    const key = raw.trim();
    if (TOOL_LABELS[key]) return TOOL_LABELS[key];
  }
  return `查阅故事资料 · 第 ${ordinal} 项`;
}

function statusLineFor(
  phase: RunPhase,
  toolCount: number,
  candidateText: string,
  sawStarted: boolean,
  terminalMessage: string | null,
): string {
  const words = countWords(candidateText);
  switch (phase) {
    case "queued":
      return "排队中，准备开始";
    case "orchestrating":
      return toolCount > 0
        ? `正在查阅故事资料 · 已检索 ${toolCount} 项`
        : sawStarted
          ? "正在理解你的要求"
          : "排队中，准备开始";
    case "composing":
      return `正在起草正文 · ${words} 字`;
    case "completed":
      return words > 0 ? `已完成 · 候选稿 ${words} 字` : "已完成";
    case "failed":
      return terminalMessage ? `未完成 · ${terminalMessage}` : "未完成";
    case "cancelled":
      return "已停下";
  }
}

function authorMessage(payload: Record<string, unknown>, fallback: string): string {
  // Surface an author-legible reason; never raw codes/stack/provider text.
  const raw = payload.message ?? payload.error_message ?? payload.reason;
  if (typeof raw === "string" && raw.trim().length > 0) {
    return sanitize(raw);
  }
  return fallback;
}

/** Strip technical noise (codes, ids, english stack fragments) from a message. */
function sanitize(text: string): string {
  return text
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "")
    .replace(/\b[A-Z][A-Z0-9_]{6,}\b/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function countWords(text: string): number {
  return text.replace(/\s/g, "").length;
}
