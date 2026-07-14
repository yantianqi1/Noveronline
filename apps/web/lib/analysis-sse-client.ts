import type { WorkflowRunEvent } from "./api";
import {
  analysisStreamReachedTerminal,
  latestWorkflowEventId,
  mergeWorkflowRunEvents,
} from "./overview-analysis-activity";

export type AnalysisStreamTransport = "sse" | "poll" | "idle";

export type AnalysisStreamHandlers = {
  onEvents: (events: WorkflowRunEvent[]) => void;
  onConnection: (
    state: "streaming" | "reconnecting" | "interrupted" | "idle",
    transport: AnalysisStreamTransport,
  ) => void;
  onTerminal?: () => void;
};

/**
 * Prefer held-open SSE with after_event_id resume; fall back to JSON polling.
 * Terminal only when analysis.run.completed/failed/cancelled arrives.
 */
export function connectAnalysisEventStream(options: {
  tenantSlug: string;
  projectId: string;
  runId: string;
  initialEvents?: readonly WorkflowRunEvent[];
  pollIntervalMs?: number;
  handlers: AnalysisStreamHandlers;
}): { close: () => void } {
  const {
    tenantSlug,
    projectId,
    runId,
    initialEvents = [],
    pollIntervalMs = 1200,
    handlers,
  } = options;

  let closed = false;
  let events = [...initialEvents];
  let cursor = latestWorkflowEventId(events);
  let failureStreak = 0;
  let pollTimer: number | null = null;
  let eventSource: EventSource | null = null;
  let transport: AnalysisStreamTransport = "idle";

  const baseUrl = () => {
    const source = new URL(
      `/api/analysis-events/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(projectId)}`,
      window.location.origin,
    );
    source.searchParams.set("runId", runId);
    if (cursor) {
      source.searchParams.set("after_event_id", cursor);
    }
    return source;
  };

  const adopt = (incoming: WorkflowRunEvent[]) => {
    if (incoming.length === 0) return;
    events = mergeWorkflowRunEvents(events, incoming);
    cursor = latestWorkflowEventId(events);
    handlers.onEvents(events);
    if (analysisStreamReachedTerminal(events)) {
      handlers.onTerminal?.();
      handlers.onConnection("idle", transport);
      close();
    }
  };

  const startPolling = () => {
    if (closed) return;
    transport = "poll";
    handlers.onConnection("streaming", "poll");
    const tick = async () => {
      if (closed || document.visibilityState !== "visible") return;
      try {
        const response = await fetch(baseUrl(), { cache: "no-store" });
        if (!response.ok) throw new Error(`poll ${response.status}`);
        const payload = (await response.json()) as { items?: WorkflowRunEvent[] };
        const incoming = Array.isArray(payload.items) ? payload.items : [];
        failureStreak = 0;
        handlers.onConnection("streaming", "poll");
        adopt(incoming);
      } catch {
        failureStreak += 1;
        handlers.onConnection(failureStreak >= 3 ? "interrupted" : "reconnecting", "poll");
      }
    };
    void tick();
    pollTimer = window.setInterval(() => void tick(), Math.max(700, pollIntervalMs));
  };

  const startSSE = () => {
    if (closed || typeof EventSource === "undefined") {
      startPolling();
      return;
    }
    const url = baseUrl();
    url.searchParams.set("stream", "1");
    eventSource = new EventSource(url.toString());
    transport = "sse";
    handlers.onConnection("streaming", "sse");

    eventSource.addEventListener("workflow.event", (message) => {
      if (closed) return;
      failureStreak = 0;
      handlers.onConnection("streaming", "sse");
      try {
        const event = JSON.parse((message as MessageEvent).data) as WorkflowRunEvent;
        if (event?.event_id) {
          adopt([event]);
        }
      } catch {
        // ignore malformed frames
      }
    });

    eventSource.onmessage = (message) => {
      if (closed) return;
      try {
        const event = JSON.parse(message.data) as WorkflowRunEvent;
        if (event?.event_id) {
          failureStreak = 0;
          handlers.onConnection("streaming", "sse");
          adopt([event]);
        }
      } catch {
        // ignore
      }
    };

    eventSource.onerror = () => {
      if (closed) return;
      failureStreak += 1;
      handlers.onConnection(failureStreak >= 3 ? "interrupted" : "reconnecting", "sse");
      if (failureStreak >= 2) {
        eventSource?.close();
        eventSource = null;
        startPolling();
      }
    };
  };

  const close = () => {
    closed = true;
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    eventSource?.close();
    eventSource = null;
  };

  if (analysisStreamReachedTerminal(events)) {
    handlers.onConnection("idle", "idle");
  } else {
    startSSE();
  }

  return { close };
}
