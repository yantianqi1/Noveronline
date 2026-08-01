"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelWriterRun,
  fetchWriterDraft,
  fetchWriterRun,
  streamWriterRunEvents,
  WriterError,
} from "@/lib/api/writer-client";
import { reconcileWriterRunStatus, reduceWriterRun, type WriterRunState } from "@/lib/api/writer-run";
import type { WriterEvent, WriterRun } from "@/lib/api/writer-types";

/**
 * Drives one live writer run: starts it, then reads the held-open SSE stream
 * with a resumable event-id cursor, reducing events into a `WriterRunState` for
 * the UI. The bounded stream reconnects until a terminal phase; a refresh of
 * run detail reconciles the authoritative status. Cancelling sends
 * the request to the server and waits for the terminal event — never assumes.
 *
 * Once the run saves its draft, the hook also follows that draft: its status
 * flips to "adopted" the moment the author adopts the candidate (here or in
 * another tab), and on completion the full body text is loaded so the rail
 * can keep showing exactly what was drafted.
 */

const SSE_RECONNECT_MS = 250;

export type LiveRun = {
  runId: string;
  state: WriterRunState;
  /** Raw events, for the collapsible technical drawer. */
  events: WriterEvent[];
  /** The saved draft's live status/text, once writer.draft.saved has landed. */
  draft: { draftId: string; status: string; contentText: string | null } | null;
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
  const [draft, setDraft] = useState<LiveRun["draft"]>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);

  const cursorRef = useRef<string | undefined>(undefined);
  const seenRef = useRef<Set<string>>(new Set());
  const streamAbortRef = useRef<AbortController | null>(null);
  const stopRef = useRef(false);
  // Draft id the reducer has surfaced so far; the stream syncs it below.
  const draftIdRef = useRef<string | null>(null);

  const state = reconcileWriterRunStatus(reduceWriterRun(events), runStatus);
  draftIdRef.current = state.draftId;

  const acceptEvent = useCallback((event: WriterEvent) => {
    if (stopRef.current || seenRef.current.has(event.event_id)) return;
    seenRef.current.add(event.event_id);
    cursorRef.current = event.event_id;
    if (event.event_type === "writer.draft.saved") {
      const draftId = event.payload?.draft_id;
      if (typeof draftId === "string" && draftId.trim()) draftIdRef.current = draftId;
    }
    setEvents((prev) => mergeEvents(prev, [event]));
  }, []);

  const syncRunDetail = useCallback(async (): Promise<string | null> => {
    if (!selection || !runId || stopRef.current) return null;
    try {
      const detail: WriterRun = await fetchWriterRun(selection.project_id, selection.tenant_id, runId);
      if (stopRef.current) return detail.status;
      setRunStatus(detail.status);
      const terminal = isTerminalStatus(detail.status);
      // Follow the saved draft: its status is the adoption source of truth for
      // a live turn, and the completed run's body text backs the settled card.
      // Every tick while terminal so an adopt from another surface (or this
      // one) flips the turn into its settled state without a page refresh.
      const draftId = draftIdRef.current;
      if (draftId) {
        try {
          const saved = await fetchWriterDraft(
            selection.project_id,
            selection.tenant_id,
            draftId,
            terminal,
          );
          if (stopRef.current) return detail.status;
          const contentText = terminal ? saved.content_text ?? null : null;
          setDraft((prev) =>
            prev?.draftId === draftId
              ? { ...prev, status: saved.status, contentText: contentText ?? prev.contentText }
              : { draftId, status: saved.status, contentText },
          );
        } catch {
          // The draft row may not be visible yet (event raced the write); the
          // The next stream reconnect retries the read; terminal runs retry from
          // the effect below.
        }
      }
      return detail.status;
    } catch (error) {
      if (error instanceof WriterError && error.status === 401) {
        stopRef.current = true;
      }
      throw error;
    }
  }, [selection, runId]);

  const stream = useCallback(async () => {
    if (!selection || !runId) return;
    while (!stopRef.current) {
      const controller = new AbortController();
      streamAbortRef.current = controller;
      try {
        await streamWriterRunEvents(
          selection.project_id,
          selection.tenant_id,
          runId,
          cursorRef.current,
          controller.signal,
          acceptEvent,
        );
        const status = await syncRunDetail();
        if (status && isTerminalStatus(status)) {
          stopRef.current = true;
          break;
        }
      } catch (error) {
        if (controller.signal.aborted || stopRef.current) break;
        if (error instanceof WriterError && error.status === 401) break;
        // A closed hold window or transient network failure is recoverable.
      } finally {
        if (streamAbortRef.current === controller) streamAbortRef.current = null;
      }
      if (stopRef.current) break;
      await delay(SSE_RECONNECT_MS);
    }
  }, [acceptEvent, runId, selection, syncRunDetail]);

  useEffect(() => {
    if (!selection || !runId) return;
    stopRef.current = false;
    cursorRef.current = undefined;
    seenRef.current = new Set();
    draftIdRef.current = null;
    setEvents([]);
    setDraft(null);
    setRunStatus(null);
    void stream();
    return () => {
      stopRef.current = true;
      streamAbortRef.current?.abort();
      streamAbortRef.current = null;
    };
  }, [selection, runId, stream]);

  // Terminal runs stop the stream, so a late draft-status change (adoption
  // from another surface) is re-synced once via this one-shot fetch.
  useEffect(() => {
    if (!selection || !state.isTerminal || !state.draftId) return;
    if (draft?.status === "adopted") return;
    let cancelled = false;
    void fetchWriterDraft(selection.project_id, selection.tenant_id, state.draftId, true)
      .then((saved) => {
        if (cancelled) return;
        setDraft({
          draftId: saved.draft_id,
          status: saved.status,
          contentText: saved.content_text ?? null,
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // Only re-run when the run's own terminal/draft identity changes — not on
    // every events-array update.
  }, [selection, state.isTerminal, state.draftId, draft?.status]);

  const cancel = useCallback(() => {
    if (!selection || !csrfToken || !runId || cancelling) return;
    setCancelling(true);
    void cancelWriterRun(selection.project_id, selection.tenant_id, csrfToken, runId)
      .catch(() => {
      // surfaced via the run's eventual terminal state; keep the stream loop
      })
      .finally(() => setCancelling(false));
  }, [selection, csrfToken, runId, cancelling]);

  if (!runId) return null;
  return { runId, state, events, draft, cancel, cancelling };
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

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
