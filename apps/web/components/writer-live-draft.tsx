"use client";

import { LoaderCircle, Sparkles, Wifi, WifiOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { WriterRunEvent } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { writerDraftText, writerStreamReachedTerminal } from "../lib/writer-event-store";
import { connectWriterEventStream, type WriterStreamTransport } from "../lib/writer-sse-client";
import { activityItemsFromEvents, WriterActivityTimeline } from "./writer-activity-timeline";
import { WriterApprovalCard, type WriterApproval } from "./writer-approval-card";

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
};

/**
 * Incremental writer draft renderer with SSE-first transport and poll fallback.
 *
 * Replaces whole-page polling: while a run is active this streams events after the
 * current cursor, merges them into a normalized set, and renders the draft from
 * selectors. On a terminal event it asks the server once for an authoritative
 * snapshot (`router.refresh()`), then stops.
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
}: WriterLiveDraftProps) {
  const router = useRouter();
  const [events, setEvents] = useState<WriterRunEvent[]>(initialEvents);
  const [connection, setConnection] = useState<ConnectionState>(active ? "streaming" : "idle");
  const [transport, setTransport] = useState<WriterStreamTransport>("idle");
  const refreshedRef = useRef(false);

  useEffect(() => {
    setEvents(initialEvents);
    refreshedRef.current = false;
  }, [initialEvents, runId]);

  useEffect(() => {
    if (!active || !runId) {
      setConnection("idle");
      setTransport("idle");
      return;
    }
    if (writerStreamReachedTerminal(events) && !refreshedRef.current) {
      refreshedRef.current = true;
      router.refresh();
      setConnection("idle");
      return;
    }
    if (writerStreamReachedTerminal(events)) {
      setConnection("idle");
      return;
    }

    const session = connectWriterEventStream({
      tenantSlug,
      projectId,
      runId,
      initialEvents: events,
      pollIntervalMs: intervalMs,
      handlers: {
        onEvents: (merged) => setEvents(merged),
        onConnection: (state, nextTransport) => {
          setConnection(state);
          setTransport(nextTransport);
        },
        onTerminal: () => {
          if (!refreshedRef.current) {
            refreshedRef.current = true;
            router.refresh();
          }
        },
      },
    });
    return () => session.close();
    // Intentionally re-subscribe when run identity / active flips; events identity is internal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, runId, tenantSlug, projectId, intervalMs, router]);

  const draftText = writerDraftText(events);
  const activityItems = useMemo(() => activityItemsFromEvents(locale, events), [events, locale]);
  const approvals = useMemo(() => approvalsFromEvents(events), [events]);

  return (
    <>
      <ConnectionBanner connection={connection} locale={locale} transport={transport} />
      <WriterActivityTimeline locale={locale} items={activityItems} />
      {approvals.map((approval) => (
        <WriterApprovalCard
          key={approval.approvalId}
          locale={locale}
          approval={approval}
          decideAction={decideApprovalAction}
        />
      ))}
      {draftText ? (
        <div className="writer-agent-draft">
          <p>{draftText}</p>
        </div>
      ) : (
        <div className="writer-agent-working" data-active={active ? "true" : "false"}>
          {active ? (
            <LoaderCircle aria-hidden="true" className="is-spinning" size={17} />
          ) : (
            <Sparkles aria-hidden="true" size={17} />
          )}
          <span>
            {active
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

function stringField(payload: Record<string, unknown> | undefined, key: string) {
  const value = payload?.[key];
  return typeof value === "string" ? value : "";
}

function ConnectionBanner({
  connection,
  locale,
  transport,
}: {
  connection: ConnectionState;
  locale: Locale;
  transport: WriterStreamTransport;
}) {
  if (connection === "streaming" || connection === "idle") {
    return null;
  }
  const interrupted = connection === "interrupted";
  return (
    <div
      className="writer-connection-banner"
      data-state={connection}
      data-transport={transport}
      role={interrupted ? "alert" : "status"}
    >
      {interrupted ? <WifiOff aria-hidden="true" size={15} /> : <Wifi aria-hidden="true" size={15} />}
      <span>
        {interrupted
          ? tx(locale, "实时更新已中断。", "Live updates were interrupted.")
          : tx(locale, "正在重新连接实时更新……", "Reconnecting to live updates...")}
      </span>
    </div>
  );
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
