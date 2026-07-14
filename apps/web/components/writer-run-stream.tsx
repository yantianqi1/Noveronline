"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import type { WriterRunEvent } from "../lib/api";
import { writerStreamReachedTerminal } from "../lib/writer-event-store";
import { connectWriterEventStream, type WriterStreamTransport } from "../lib/writer-sse-client";

export type WriterConnectionState = "streaming" | "reconnecting" | "interrupted" | "idle";

type WriterRunStreamValue = {
  runId: string;
  /** True while the selected run is queued/running (before a terminal event). */
  active: boolean;
  events: WriterRunEvent[];
  connection: WriterConnectionState;
  transport: WriterStreamTransport;
};

const WriterRunStreamContext = createContext<WriterRunStreamValue | null>(null);

type WriterRunStreamProviderProps = {
  active: boolean;
  runId: string;
  tenantSlug: string;
  projectId: string;
  initialEvents: WriterRunEvent[];
  intervalMs?: number;
  children: ReactNode;
};

/**
 * Single writer-event stream for the whole workbench.
 *
 * Owns the SSE-first / poll-fallback connection for the selected run and fans the
 * merged event set out to every consumer (task status line in the conversation
 * rail, candidate stream on the artifact canvas). On a terminal event it asks the
 * server once for an authoritative snapshot (`router.refresh()`), then stops.
 */
export function WriterRunStreamProvider({
  active,
  runId,
  tenantSlug,
  projectId,
  initialEvents,
  intervalMs = 900,
  children,
}: WriterRunStreamProviderProps) {
  const router = useRouter();
  const [events, setEvents] = useState<WriterRunEvent[]>(initialEvents);
  const [connection, setConnection] = useState<WriterConnectionState>(active ? "streaming" : "idle");
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
    if (writerStreamReachedTerminal(events)) {
      if (!refreshedRef.current) {
        refreshedRef.current = true;
        router.refresh();
      }
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

  const streamStillActive = active && !writerStreamReachedTerminal(events);

  return (
    <WriterRunStreamContext.Provider
      value={{ runId, active: streamStillActive, events, connection, transport }}
    >
      {children}
    </WriterRunStreamContext.Provider>
  );
}

/** Merged writer-run stream for the selected run, or null outside a provider. */
export function useWriterRunStream(): WriterRunStreamValue | null {
  return useContext(WriterRunStreamContext);
}
