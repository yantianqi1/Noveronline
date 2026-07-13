import type { WriterRunEvent } from "./api";
import { latestWriterCursor, mergeWriterEvents, writerStreamReachedTerminal } from "./writer-event-store";

export type WriterStreamTransport = "sse" | "poll" | "idle";

export type WriterStreamHandlers = {
  onEvents: (events: WriterRunEvent[]) => void;
  onConnection: (state: "streaming" | "reconnecting" | "interrupted" | "idle", transport: WriterStreamTransport) => void;
  onTerminal?: () => void;
};

/**
 * Prefer held-open SSE with Last-Event-ID resume; fall back to incremental JSON polling.
 * Never treats a closed socket alone as terminal — only terminal event types do.
 */
export function connectWriterEventStream(options: {
  tenantSlug: string;
  projectId: string;
  runId: string;
  initialEvents?: readonly WriterRunEvent[];
  pollIntervalMs?: number;
  handlers: WriterStreamHandlers;
}): { close: () => void } {
  const {
    tenantSlug,
    projectId,
    runId,
    initialEvents = [],
    pollIntervalMs = 900,
    handlers,
  } = options;

  let closed = false;
  let events = [...initialEvents];
  let cursor = latestWriterCursor(events);
  let failureStreak = 0;
  let pollTimer: number | null = null;
  let eventSource: EventSource | null = null;
  let transport: WriterStreamTransport = "idle";

  const baseUrl = () => {
    const source = new URL(
      `/api/writer-events/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(projectId)}`,
      window.location.origin,
    );
    source.searchParams.set("runId", runId);
    if (cursor) {
      source.searchParams.set("after_event_id", cursor);
    }
    return source;
  };

  const adopt = (incoming: WriterRunEvent[]) => {
    if (incoming.length === 0) return;
    events = mergeWriterEvents(events, incoming);
    cursor = latestWriterCursor(events);
    handlers.onEvents(events);
    if (writerStreamReachedTerminal(events)) {
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
        const payload = (await response.json()) as { items?: WriterRunEvent[] };
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
    pollTimer = window.setInterval(() => void tick(), Math.max(600, pollIntervalMs));
  };

  const startSSE = () => {
    if (closed || typeof EventSource === "undefined") {
      startPolling();
      return;
    }
    const url = baseUrl();
    url.searchParams.set("stream", "1");
    // EventSource cannot set Last-Event-ID header on first open; query cursor covers resume.
    eventSource = new EventSource(url.toString());
    transport = "sse";
    handlers.onConnection("streaming", "sse");

    eventSource.addEventListener("workflow.event", (message) => {
      if (closed) return;
      failureStreak = 0;
      handlers.onConnection("streaming", "sse");
      try {
        const event = JSON.parse((message as MessageEvent).data) as WriterRunEvent;
        if (event?.event_id) {
          adopt([event]);
        }
      } catch {
        // ignore malformed frames; keep stream open
      }
    });

    eventSource.onmessage = (message) => {
      if (closed) return;
      try {
        const event = JSON.parse(message.data) as WriterRunEvent;
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
      // Fall back to polling after sustained SSE failure.
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

  if (writerStreamReachedTerminal(events)) {
    handlers.onConnection("idle", "idle");
  } else {
    startSSE();
  }

  return { close };
}
