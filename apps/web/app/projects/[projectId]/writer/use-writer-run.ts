"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelWriterRun,
  fetchRunEvents,
  fetchWriterRun,
  WriterError,
} from "@/lib/api/writer-client";
import { reduceWriterRun, type WriterRunState } from "@/lib/api/writer-run";
import type { WriterEvent, WriterRun } from "@/lib/api/writer-types";

/**
 * Drives one live writer run: starts it, then polls the event stream with a
 * resumable cursor (the endpoint pages at 100 with no cursor), reducing events
 * into a `WriterRunState` for the UI. Polling stops at a terminal phase; a
 * refresh of run detail reconciles the authoritative status. Cancelling sends
 * the request to the server and waits for the terminal event — never assumes.
 */

const POLL_MS = 900;
const PAGE_SIZE = 100;

export type LiveRun = {
  runId: string;
  state: WriterRunState;
  /** Raw events, for the collapsible technical drawer. */
  events: WriterEvent[];
  cancel: () => void;
  cancelling: boolean;
};

export function useWriterRun(
  selection: { tenant_id: string; project_id: string } | null,
  csrfToken: string | null,
  runId: string | null,
): LiveRun | null {
  const [events, setEvents] = useState<WriterEvent[]>([]);
  const [cancelling, setCancelling] = useState(false);

  const cursorRef = useRef<string | undefined>(undefined);
  const seenRef = useRef<Set<string>>(new Set());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopRef = useRef(false);

  const state = reduceWriterRun(events);

  const poll = useCallback(async () => {
    if (!selection || !runId || stopRef.current) return;
    try {
      // Chase the 100-per-page cursor until a short page marks the end.
      let after = cursorRef.current;
      for (;;) {
        const page = await fetchRunEvents(selection.project_id, selection.tenant_id, runId, after);
        if (stopRef.current) return;
        const fresh = page.filter((e) => !seenRef.current.has(e.event_id));
        if (fresh.length > 0) {
          for (const e of fresh) seenRef.current.add(e.event_id);
          setEvents((prev) => mergeEvents(prev, fresh));
          after = page[page.length - 1].event_id;
          cursorRef.current = after;
        }
        if (page.length < PAGE_SIZE) break;
      }
      // Reconcile authoritative status; stop polling once terminal.
      const detail: WriterRun = await fetchWriterRun(selection.project_id, selection.tenant_id, runId);
      if (isTerminalStatus(detail.status)) {
        stopRef.current = true;
        if (timerRef.current) clearInterval(timerRef.current);
      }
    } catch (error) {
      // A dropped poll is non-fatal — the next tick retries from the cursor.
      // Only stop on an auth failure, which won't recover by itself.
      if (error instanceof WriterError && error.status === 401) {
        stopRef.current = true;
        if (timerRef.current) clearInterval(timerRef.current);
      }
    }
  }, [selection, runId]);

  useEffect(() => {
    if (!selection || !runId) return;
    stopRef.current = false;
    cursorRef.current = undefined;
    seenRef.current = new Set();
    setEvents([]);
    void poll();
    timerRef.current = setInterval(() => {
      void poll();
    }, POLL_MS);
    return () => {
      stopRef.current = true;
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [selection, runId, poll]);

  const cancel = useCallback(() => {
    if (!selection || !csrfToken || !runId || cancelling) return;
    setCancelling(true);
    void cancelWriterRun(selection.project_id, selection.tenant_id, csrfToken, runId)
      .catch(() => {
        // surfaced via the run's eventual terminal state; keep polling
      })
      .finally(() => setCancelling(false));
  }, [selection, csrfToken, runId, cancelling]);

  if (!runId) return null;
  return { runId, state, events, cancel, cancelling };
}

function mergeEvents(existing: WriterEvent[], incoming: WriterEvent[]): WriterEvent[] {
  const seen = new Set(existing.map((e) => e.event_id));
  const merged = [...existing];
  for (const e of incoming) if (!seen.has(e.event_id)) merged.push(e);
  merged.sort((a, b) => a.sequence - b.sequence);
  return merged;
}

function isTerminalStatus(status: string): boolean {
  const s = status.toLowerCase();
  return s === "completed" || s === "failed" || s === "cancelled" || s === "canceled";
}
