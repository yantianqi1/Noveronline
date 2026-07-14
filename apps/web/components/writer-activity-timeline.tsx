"use client";

import {
  BookOpen,
  CircleAlert,
  CircleCheck,
  FilePenLine,
  LoaderCircle,
  Search,
  Wrench,
} from "lucide-react";

import type { WriterRunEvent } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";
import { WriterContextChip, type ContextChipKind } from "./writer-context-chip";

export type ActivityItem = {
  id: string;
  kind: "tool" | "retrieve" | "write" | "status" | "approval" | "revision";
  status: "running" | "completed" | "failed" | "pending";
  title: string;
  detail?: string;
  at?: string;
  chips?: { kind: ContextChipKind; label: string; id?: string }[];
};

type WriterActivityTimelineProps = {
  locale: Locale;
  items: ActivityItem[];
};

/**
 * One row per meaningful agent action (not per token).
 * Tool / retrieve / write are color-coded; order is chronological.
 */
export function WriterActivityTimeline({ locale, items }: WriterActivityTimelineProps) {
  if (items.length === 0) {
    return (
      <p className="form-hint writer-activity-empty">
        <Bi zh="Agent 活动将显示在此时间线。" en="Agent activity will appear on this timeline." />
      </p>
    );
  }

  return (
    <ol className="writer-activity-timeline" aria-label={tx(locale, "活动时间线", "Activity timeline")}>
      {items.map((item) => (
        <li key={item.id} className="writer-activity-item" data-kind={item.kind} data-status={item.status}>
          <span className="writer-activity-icon" aria-hidden="true">
            <ActivityIcon kind={item.kind} status={item.status} />
          </span>
          <div className="writer-activity-body">
            <div className="writer-activity-title-row">
              <strong>{item.title}</strong>
              {item.at ? <time dateTime={item.at}>{formatTime(item.at)}</time> : null}
            </div>
            {item.detail ? <p>{item.detail}</p> : null}
            {item.chips && item.chips.length > 0 ? (
              <div className="writer-activity-chips">
                {item.chips.map((chip, index) => (
                  <WriterContextChip key={`${chip.kind}-${chip.id ?? index}`} kind={chip.kind} label={chip.label} />
                ))}
              </div>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

const RUN_LIFECYCLE_ID = "writer-run-lifecycle";

/**
 * Build a compact activity list. Run lifecycle is one reconciled row
 * (started → completed/failed/cancelled) so the started spinner never
 * stays forever next to a terminal status.
 *
 * Routine tool started/completed pairs collapse into a single completed
 * row; only high-signal kinds stay expanded by default.
 */
export function activityItemsFromEvents(locale: Locale, events: readonly WriterRunEvent[]): ActivityItem[] {
  const items: ActivityItem[] = [];
  let runLifecycle: ActivityItem | null = null;
  let runModeDetail: string | undefined;
  const openTools = new Map<string, number>();

  for (const event of events) {
    if (event.event_type === "writer.token") {
      continue;
    }
    const payload = event.payload ?? {};

    if (event.event_type === "writer.run.started") {
      runModeDetail = stringField(payload, "mode") || undefined;
      runLifecycle = {
        id: RUN_LIFECYCLE_ID,
        kind: "status",
        status: "running",
        title: tx(locale, "写作任务进行中", "Writer run in progress"),
        detail: runModeDetail,
        at: event.created_at,
      };
      continue;
    }
    if (event.event_type === "writer.run.completed") {
      runLifecycle = {
        id: RUN_LIFECYCLE_ID,
        kind: "status",
        status: "completed",
        title: tx(locale, "写作任务完成", "Writer run completed"),
        detail: runModeDetail,
        at: event.created_at,
      };
      continue;
    }
    if (event.event_type === "writer.run.failed") {
      const message = stringField(payload, "message") || stringField(payload, "error");
      const code = stringField(payload, "error_code") || stringField(payload, "code");
      const fromPayload = [message, code].filter(Boolean).join(" · ");
      runLifecycle = {
        id: RUN_LIFECYCLE_ID,
        kind: "status",
        status: "failed",
        title: tx(locale, "写作任务失败", "Writer run failed"),
        detail: fromPayload || runModeDetail,
        at: event.created_at,
      };
      continue;
    }
    if (event.event_type === "writer.run.cancelled") {
      runLifecycle = {
        id: RUN_LIFECYCLE_ID,
        kind: "status",
        status: "failed",
        title: tx(locale, "写作任务已取消", "Writer run cancelled"),
        detail: runModeDetail,
        at: event.created_at,
      };
      continue;
    }

    if (event.event_type === "writer.tool.started") {
      const toolName = stringField(payload, "tool_name") || "tool";
      const item: ActivityItem = {
        id: event.event_id,
        kind: isRetrieveTool(toolName) ? "retrieve" : "tool",
        status: "running",
        title: toolStartedTitle(locale, toolName),
        detail: toolName,
        at: event.created_at,
        chips: chipsFromToolPayload(toolName, payload),
      };
      openTools.set(toolName, items.length);
      items.push(item);
      continue;
    }
    if (event.event_type === "writer.tool.completed") {
      const toolName = stringField(payload, "tool_name") || "tool";
      const isError = payload.is_error === true;
      const openIndex = openTools.get(toolName);
      const completed: ActivityItem = {
        id: event.event_id,
        kind: isRetrieveTool(toolName) ? "retrieve" : "tool",
        status: isError ? "failed" : "completed",
        title: toolCompletedTitle(locale, toolName, isError),
        detail: toolName,
        at: event.created_at,
        chips: chipsFromToolPayload(toolName, payload),
      };
      if (openIndex !== undefined && items[openIndex]?.status === "running") {
        items[openIndex] = { ...completed, id: items[openIndex].id };
        openTools.delete(toolName);
      } else {
        items.push(completed);
      }
      continue;
    }
    if (event.event_type === "writer.draft.saved") {
      items.push({
        id: event.event_id,
        kind: "write",
        status: "completed",
        title: tx(locale, "已保存候选稿", "Candidate draft saved"),
        at: event.created_at,
      });
      continue;
    }
    if (event.event_type === "writer.revision.proposed") {
      items.push({
        id: event.event_id,
        kind: "revision",
        status: "pending",
        title: tx(locale, "提出修订建议", "Proposed revision"),
        detail: stringField(payload, "instruction") || undefined,
        at: event.created_at,
      });
      continue;
    }
    if (event.event_type === "writer.approval.required") {
      items.push({
        id: event.event_id,
        kind: "approval",
        status: "pending",
        title: tx(locale, "等待你的审批", "Waiting for your approval"),
        detail: stringField(payload, "summary") || stringField(payload, "action") || undefined,
        at: event.created_at,
      });
      continue;
    }
    if (event.event_type === "writer.approval.resolved") {
      const decision = stringField(payload, "decision");
      items.push({
        id: event.event_id,
        kind: "approval",
        status: decision === "approve" ? "completed" : "failed",
        title:
          decision === "approve"
            ? tx(locale, "审批已通过", "Approval granted")
            : tx(locale, "审批已拒绝", "Approval rejected"),
        at: event.created_at,
      });
    }
  }

  // High-signal first: run lifecycle, then non-tool rows, then tools (compact).
  const highSignal = items.filter((item) => item.kind !== "tool" && item.kind !== "retrieve");
  const toolRows = items.filter((item) => item.kind === "tool" || item.kind === "retrieve");
  // Drop successful tool noise when a terminal run exists; keep failures + running.
  const toolsVisible =
    runLifecycle && runLifecycle.status !== "running"
      ? toolRows.filter((item) => item.status === "failed" || item.status === "running")
      : toolRows.filter((item) => item.status !== "completed" || toolRows.length <= 2);

  const ordered: ActivityItem[] = [];
  if (runLifecycle) {
    ordered.push(runLifecycle);
  }
  ordered.push(...highSignal, ...toolsVisible);
  return ordered;
}

function ActivityIcon({ kind, status }: { kind: ActivityItem["kind"]; status: ActivityItem["status"] }) {
  if (status === "running") return <LoaderCircle className="is-spinning" size={15} />;
  if (status === "failed") return <CircleAlert size={15} />;
  if (kind === "retrieve") return <Search size={15} />;
  if (kind === "write" || kind === "revision") return <FilePenLine size={15} />;
  if (kind === "approval") return <CircleCheck size={15} />;
  if (kind === "tool") return <Wrench size={15} />;
  return <BookOpen size={15} />;
}

function isRetrieveTool(name: string) {
  return name.startsWith("query_");
}

function toolStartedTitle(locale: Locale, toolName: string) {
  return tx(locale, `正在调用 ${toolName}`, `Calling ${toolName}`);
}

function toolCompletedTitle(locale: Locale, toolName: string, isError: boolean) {
  if (isError) return tx(locale, `${toolName} 失败`, `${toolName} failed`);
  return tx(locale, `已完成 ${toolName}`, `Completed ${toolName}`);
}

function chipsFromToolPayload(toolName: string, payload: Record<string, unknown>) {
  const chips: { kind: ContextChipKind; label: string; id?: string }[] = [];
  const kind = toolKind(toolName);
  const count =
    numberField(payload, "result_count") ??
    numberField(payload, "match_count") ??
    numberField(payload, "node_count");
  if (kind && count !== null) {
    chips.push({ kind, label: `${count}`, id: toolName });
  } else if (kind) {
    chips.push({ kind, label: toolName.replace(/^query_/, ""), id: toolName });
  }
  return chips;
}

function toolKind(toolName: string): ContextChipKind | null {
  if (toolName.includes("asset")) return "assets";
  if (toolName.includes("graph") || toolName.includes("neighbors")) return "graph";
  if (toolName.includes("world") || toolName.includes("character")) return "worldline";
  if (toolName.includes("manuscript") || toolName.includes("chapter")) return "manuscript";
  return null;
}

function stringField(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function numberField(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
