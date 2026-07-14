"use client";

import { LoaderCircle, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { WriterRunEvent } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { writerDraftText, writerStreamReachedTerminal } from "../lib/writer-event-store";
import { connectWriterEventStream } from "../lib/writer-sse-client";
import { Bi } from "./bilingual-text";
import { WriterApprovalCard, type WriterApproval } from "./writer-approval-card";
import { useWriterRunStream } from "./writer-run-stream";
import { WriterTaskStatusLine } from "./writer-task-status-line";

type ConnectionState = "streaming" | "reconnecting" | "interrupted" | "idle";

type WriterLiveDraftProps = {
  active: boolean;
  locale: Locale;
  runId: string;
  tenantSlug: string;
  projectId: string;
  initialEvents: WriterRunEvent[];
  intervalMs?: number;
  decideApprovalAction?: (formData: FormData) => Promise<void>;
  /** When true, prose lives on the canvas sheet — dock only shows status + summary. */
  proseOnCanvas?: boolean;
};

/**
 * Dock-side run narrative: collapsed status line, approvals, and (optionally) a
 * short summary pointing at the canvas candidate. Prefer the shared
 * WriterRunStreamProvider when mounted to avoid a second SSE subscription.
 */
export function WriterLiveDraft({
  active,
  locale,
  runId,
  tenantSlug,
  projectId,
  initialEvents,
  intervalMs = 900,
  decideApprovalAction,
  proseOnCanvas = true,
}: WriterLiveDraftProps) {
  const shared = useWriterRunStream();
  const useShared = shared !== null && shared.runId === runId;

  const router = useRouter();
  const [localEvents, setLocalEvents] = useState<WriterRunEvent[]>(initialEvents);
  const [localConnection, setLocalConnection] = useState<ConnectionState>(active ? "streaming" : "idle");
  const refreshedRef = useRef(false);

  useEffect(() => {
    if (useShared) return;
    setLocalEvents(initialEvents);
    refreshedRef.current = false;
  }, [initialEvents, runId, useShared]);

  useEffect(() => {
    if (useShared) return;
    if (!active || !runId) {
      setLocalConnection("idle");
      return;
    }
    if (writerStreamReachedTerminal(localEvents) && !refreshedRef.current) {
      refreshedRef.current = true;
      router.refresh();
      setLocalConnection("idle");
      return;
    }
    if (writerStreamReachedTerminal(localEvents)) {
      setLocalConnection("idle");
      return;
    }

    const session = connectWriterEventStream({
      tenantSlug,
      projectId,
      runId,
      initialEvents: localEvents,
      pollIntervalMs: intervalMs,
      handlers: {
        onEvents: (merged) => setLocalEvents(merged),
        onConnection: (state) => setLocalConnection(state),
        onTerminal: () => {
          if (!refreshedRef.current) {
            refreshedRef.current = true;
            router.refresh();
          }
        },
      },
    });
    return () => session.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [useShared, active, runId, tenantSlug, projectId, intervalMs, router]);

  const events = useShared ? shared.events : localEvents;
  const connection = useShared ? shared.connection : localConnection;
  const streamActive = useShared ? shared.active : active && !writerStreamReachedTerminal(events);
  const draftText = writerDraftText(events);
  const charCount = [...draftText].length;
  const approvals = useMemo(() => approvalsFromEvents(events), [events]);

  return (
    <>
      <WriterTaskStatusLine connection={connection} events={events} locale={locale} />
      {approvals.map((approval) => (
        <WriterApprovalCard
          key={approval.approvalId}
          locale={locale}
          approval={approval}
          decideAction={decideApprovalAction}
        />
      ))}
      {proseOnCanvas ? (
        <div className="writer-result-summary">
          {draftText ? (
            <p>
              <Bi
                zh={`候选稿已写好（${charCount} 字），见左侧画布。`}
                en={`Candidate draft ready (${charCount} characters) — see the canvas.`}
              />
            </p>
          ) : streamActive ? (
            <p className="writer-agent-working" data-active="true">
              <LoaderCircle aria-hidden="true" className="is-spinning" size={17} />
              <span>
                <Bi zh="产物正在左侧画布生成…" en="The artifact is forming on the canvas…" />
              </span>
            </p>
          ) : (
            <p className="writer-agent-working" data-active="false">
              <Sparkles aria-hidden="true" size={17} />
              <span>
                <Bi zh="候选正文尚未生成。" en="No candidate prose was generated." />
              </span>
            </p>
          )}
        </div>
      ) : draftText ? (
        <div className="writer-agent-draft">
          <p>{draftText}</p>
        </div>
      ) : (
        <div className="writer-agent-working" data-active={streamActive ? "true" : "false"}>
          {streamActive ? (
            <LoaderCircle aria-hidden="true" className="is-spinning" size={17} />
          ) : (
            <Sparkles aria-hidden="true" size={17} />
          )}
          <span>
            {streamActive
              ? tx(locale, "Writer 正在组织这一段……", "Writer is shaping this passage...")
              : tx(locale, "候选正文尚未生成。", "No candidate prose was generated.")}
          </span>
        </div>
      )}
      <p className="sr-only" role="status" aria-live="polite">
        {connectionAnnouncement(connection, locale)}
      </p>
    </>
  );
}

function approvalsFromEvents(events: readonly WriterRunEvent[]): WriterApproval[] {
  const resolved = new Set<string>();
  for (const event of events) {
    if (event.event_type === "writer.approval.resolved") {
      const id = stringField(event.payload, "approval_id");
      if (id) resolved.add(id);
    }
  }
  const pending: WriterApproval[] = [];
  for (const event of events) {
    if (event.event_type !== "writer.approval.required") continue;
    const approvalId = stringField(event.payload, "approval_id") || event.event_id;
    if (resolved.has(approvalId)) continue;
    pending.push({
      approvalId,
      summary: stringField(event.payload, "summary") || "Approval required",
      consequence: stringField(event.payload, "consequence") || stringField(event.payload, "detail") || "",
      action: stringField(event.payload, "action") || undefined,
      reversible: event.payload?.reversible === true,
    });
  }
  return pending;
}

function stringField(payload: Record<string, unknown> | undefined, key: string): string {
  const value = payload?.[key];
  return typeof value === "string" ? value : "";
}

function connectionAnnouncement(connection: ConnectionState, locale: Locale) {
  switch (connection) {
    case "reconnecting":
      return tx(locale, "正在重新连接实时更新", "Reconnecting to live updates");
    case "interrupted":
      return tx(locale, "实时更新已中断", "Live updates interrupted");
    default:
      return "";
  }
}
