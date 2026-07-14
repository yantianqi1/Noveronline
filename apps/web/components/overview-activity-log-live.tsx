"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { WorkflowRunEvent } from "../lib/api";
import { connectAnalysisEventStream, type AnalysisStreamTransport } from "../lib/analysis-sse-client";
import {
  analysisActivityLogFromEvents,
  mergeWorkflowRunEvents,
  type OverviewActivityLogLine,
} from "../lib/overview-analysis-activity";
import { type Locale } from "../lib/locale";
import { Bi } from "./bilingual-text";

type OverviewActivityLogLiveProps = {
  locale: Locale;
  projectId: string;
  runId: string;
  tenantSlug: string;
  isActive: boolean;
  initialEvents: WorkflowRunEvent[];
  /** Static fallback for seed runs or when SSE is not needed. */
  staticLines?: OverviewActivityLogLine[];
  streamKind?: "analysis" | "static";
};

export function OverviewActivityLogLive({
  locale,
  projectId,
  runId,
  tenantSlug,
  isActive,
  initialEvents,
  staticLines,
  streamKind = "analysis",
}: OverviewActivityLogLiveProps) {
  const router = useRouter();
  const [events, setEvents] = useState<WorkflowRunEvent[]>(initialEvents);
  const [connection, setConnection] = useState<"streaming" | "reconnecting" | "interrupted" | "idle">(
    isActive ? "streaming" : "idle",
  );
  const [transport, setTransport] = useState<AnalysisStreamTransport>(isActive ? "sse" : "idle");
  const eventsRef = useRef(events);
  eventsRef.current = events;

  useEffect(() => {
    setEvents((previous) => mergeWorkflowRunEvents(previous, initialEvents));
  }, [runId, initialEvents]);

  useEffect(() => {
    if (streamKind !== "analysis" || !runId || !isActive) {
      setConnection("idle");
      setTransport("idle");
      return;
    }
    const session = connectAnalysisEventStream({
      tenantSlug,
      projectId,
      runId,
      initialEvents: eventsRef.current,
      handlers: {
        onEvents: (next) => setEvents(next),
        onConnection: (state, nextTransport) => {
          setConnection(state);
          setTransport(nextTransport);
        },
        onTerminal: () => {
          router.refresh();
        },
      },
    });
    return () => session.close();
  }, [streamKind, runId, isActive, tenantSlug, projectId, router]);

  const lines = useMemo(() => {
    if (streamKind === "static" && staticLines) {
      // Newest first for consistency with live analysis log.
      return [...staticLines].reverse();
    }
    return analysisActivityLogFromEvents(locale, events);
  }, [streamKind, staticLines, locale, events]);

  const liveLabel = connection === "streaming" && transport === "sse"
    ? <Bi zh="实时 SSE" en="Live SSE" />
    : connection === "streaming" && transport === "poll"
      ? <Bi zh="实时轮询" en="Live poll" />
      : connection === "reconnecting"
        ? <Bi zh="重连中" en="Reconnecting" />
        : connection === "interrupted"
          ? <Bi zh="连接中断" en="Interrupted" />
          : isActive
            ? <Bi zh="实时" en="Live" />
            : null;

  // Cap the author-facing list even if upstream sent a large buffer.
  const visibleLines = lines.slice(0, 24);

  if (visibleLines.length === 0) {
    if (!isActive) return null;
    return (
      <p className="form-hint overview-activity-log-empty">
        <Bi zh="分析进行中，关键节点会显示在这里…" en="Analysis is running; key milestones appear here…" />
      </p>
    );
  }

  return (
    <div className="overview-activity-log" data-active={isActive ? "true" : "false"} data-transport={transport}>
      <div className="overview-activity-log-header">
        <span><Bi zh="关键进度" en="Key progress" /></span>
        {liveLabel ? (
          <span className="overview-activity-log-live" data-state={connection}>
            {liveLabel}
          </span>
        ) : null}
      </div>
      <ol className="overview-activity-log-list" aria-live={isActive ? "polite" : "off"}>
        {visibleLines.map((line, index) => (
          <li data-tone={line.tone} data-latest={index === 0 ? "true" : "false"} key={line.id}>
            <span className="overview-activity-log-dot" aria-hidden="true" />
            <span className="overview-activity-log-message">{line.message}</span>
            {line.timeLabel ? (
              <time className="overview-activity-log-time">{line.timeLabel}</time>
            ) : null}
          </li>
        ))}
      </ol>
      {lines.length > visibleLines.length ? (
        <p className="form-hint overview-activity-log-more">
          <Bi
            zh="仅显示最近进度；更早的工具与产出已折叠。"
            en="Showing recent progress; earlier tool and artifact lines are folded."
          />
        </p>
      ) : null}
    </div>
  );
}
