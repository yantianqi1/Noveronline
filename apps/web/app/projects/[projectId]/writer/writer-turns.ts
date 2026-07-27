"use client";

import type { WriterMessage } from "@/lib/api/writer-types";

import type { ConversationTurn } from "./writer-rail";

/**
 * Fold persistent thread history into rail turns. Kept in its own module (not
 * the rail component) so node --test can import it without pulling in React.
 *
 * User messages anchor requests; the run_id a message carries anchors that
 * request's task card directly after it (deduped, so the user message and its
 * agent status line attach exactly one card). Agent lines collapse into the
 * task card, so standalone agent messages are only kept when they carry no
 * run of their own.
 */
export function buildConversationTurns(messages: WriterMessage[]): ConversationTurn[] {
  const turns: ConversationTurn[] = [];
  // Runs that already anchored a task card, plus every run_id seen anywhere —
  // a later message carrying the same run must not spawn a second card, even
  // if the first mention wasn't the one that placed the card.
  const seenRunIds = new Set<string>();
  const anchoredRunIds = new Set<string>();
  for (const message of messages) {
    if (message.role === "system" || message.role === "approval") continue;
    const runId = typeof message.run_id === "string" && message.run_id.length > 0 ? message.run_id : null;
    if (message.role === "agent" && runId && (anchoredRunIds.has(runId) || seenRunIds.has(runId))) {
      // The task card already tells this turn's story; skip the echo line.
      continue;
    }
    if (message.role === "agent") {
      turns.push({ kind: "agent", id: message.message_id, body: message.body });
    } else {
      turns.push({ kind: "user", id: message.message_id, body: message.body });
    }
    if (!runId || seenRunIds.has(runId)) continue;
    seenRunIds.add(runId);
    anchoredRunIds.add(runId);
    turns.push({ kind: "task", id: `task-${runId}`, runId });
  }
  return turns;
}
