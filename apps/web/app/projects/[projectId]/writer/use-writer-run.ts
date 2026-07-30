"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelWriterRun,
  fetchRunEvents,
  fetchWriterDraft,
  fetchWriterRun,
  WriterError,
} from "@/lib/api/writer-client";
import { reconcileWriterRunStatus, reduceWriterRun, type WriterRunState } from "@/lib/api/writer-run";
import type { WriterEvent, WriterRun } from "@/lib/api/writer-types";

/**
 * Drives one live writer run: starts it, then polls the event stream with a
 * resumable cursor (the endpoint pages at 100 with no cursor), reducing events
 * into a `WriterRunState` for the UI. Polling stops at a terminal phase; a
 * refresh of run detail reconciles the authoritative status. Cancelling sends
 * the request to the server and waits for the terminal event — never assumes.
 *
 * Once the run saves its draft, the hook also follows that draft: its status
 * flips to "adopted" the moment the author adopts the candidate (here or in
 * another tab), and on completion the full body text is loaded so the rail
 * can keep showing exactly what was drafted.
 */

const POLL_MS = 900;
const PAGE_SIZE = 100;

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
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopRef = useRef(false);
  const inFlightRef = useRef(false);
  // Draft id the reducer has surfaced so far; the poll loop syncs it below.
  const draftIdRef = useRef<string | null>(null);

  const state = reconcileWriterRunStatus(reduceWriterRun(events), runStatus);
  draftIdRef.current = state.draftId;

  const poll = useCallback(async () => {
    if (!selection || !runId || stopRef.current || inFlightRef.current) return;
    inFlightRef.current = true;
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
        }
        const nextAfter = page[page.length - 1]?.event_id;
        if (nextAfter && nextAfter !== after) {
          after = nextAfter;
          cursorRef.current = nextAfter;
        } else if (page.length >= PAGE_SIZE) {
          break;
        }
        if (page.length < PAGE_SIZE) break;
      }
      // Reconcile authoritative status; stop polling once terminal.
      const detail: WriterRun = await fetchWriterRun(selection.project_id, selection.tenant_id, runId);
      if (stopRef.current) return;
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
          if (stopRef.current) return;
          const contentText = terminal ? saved.content_text ?? null : null;
          setDraft((prev) =>
            prev?.draftId === draftId
              ? { ...prev, status: saved.status, contentText: contentText ?? prev.contentText }
              : { draftId, status: saved.status, contentText },
          );
        } catch {
          // The draft row may not be visible yet (event raced the write); the
          // next poll tick retries. Terminal runs retry from the effect below.
        }
      }
      if (terminal) {
        const finalPage = await fetchRunEvents(selection.project_id, selection.tenant_id, runId, cursorRef.current);
        const finalFresh = finalPage.filter((event) => !seenRef.current.has(event.event_id));
        if (finalFresh.length > 0) {
          finalFresh.forEach((event) => seenRef.current.add(event.event_id));
          setEvents((prev) => mergeEvents(prev, finalFresh));
          cursorRef.current = finalPage[finalPage.length - 1]?.event_id ?? cursorRef.current;
        }
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
    } finally {
      inFlightRef.current = false;
    }
  }, [selection, runId]);

  useEffect(() => {
    if (!selection || !runId) return;
    stopRef.current = false;
    inFlightRef.current = false;
    cursorRef.current = undefined;
    seenRef.current = new Set();
    setEvents([]);
    setDraft(null);
    setRunStatus(null);
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

  // Terminal runs stop the interval, so a late draft-status change (adoption
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
        // surfaced via the run's eventual terminal state; keep polling
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
