import type { WriterRunEvent } from "./api";

/**
 * Normalized writer-event store primitives.
 *
 * The writer stream is delivered as ordered, append-only events. Clients poll for
 * increments after a cursor and merge them into a known set. These pure helpers own
 * the transport-invariants — dedupe by `event_id`, order by `sequence`, tolerate
 * out-of-order and duplicate delivery — so presentation code renders from selectors
 * instead of re-deriving stream state on every refresh.
 *
 * Selectors mirror the four-step writer pipeline used by the workbench shell so the
 * server-rendered path and the client incremental path stay behaviorally identical.
 */

/**
 * Merge incoming writer events into a known set.
 *
 * Later events with the same `event_id` replace earlier copies (last write wins on
 * identity), and the result is ordered by ascending `sequence`. Idempotent: merging
 * the same events again yields an equal set.
 */
export function mergeWriterEvents(
  known: readonly WriterRunEvent[],
  incoming: readonly WriterRunEvent[],
): WriterRunEvent[] {
  const byId = new Map<string, WriterRunEvent>();
  for (const event of known) {
    byId.set(event.event_id, event);
  }
  for (const event of incoming) {
    byId.set(event.event_id, event);
  }
  return [...byId.values()].sort((left, right) => left.sequence - right.sequence);
}

/**
 * The `event_id` of the highest-`sequence` event, for use as the next
 * `after_event_id` cursor. Returns "" when no events are known.
 */
export function latestWriterCursor(events: readonly WriterRunEvent[]): string {
  let latest: WriterRunEvent | null = null;
  for (const event of events) {
    if (latest === null || event.sequence > latest.sequence) {
      latest = event;
    }
  }
  return latest?.event_id ?? "";
}

/**
 * Assemble streamed draft prose from `writer.token` events in sequence order.
 * Input need not be pre-sorted; tokens are ordered by `sequence` before joining.
 */
export function writerDraftText(events: readonly WriterRunEvent[]): string {
  return [...events]
    .sort((left, right) => left.sequence - right.sequence)
    .filter((event) => event.event_type === "writer.token")
    .map((event) => stringValue(event.payload, "token"))
    .join("");
}

/**
 * Bounded progress stage `0..3` mirroring the writer pipeline:
 * understand (0) -> retrieve (1) -> draft (2) -> save candidate (3).
 */
export function writerProgressStage(events: readonly WriterRunEvent[]): number {
  const eventTypes = new Set(events.map((event) => event.event_type));
  if (eventTypes.has("writer.draft.saved") || eventTypes.has("writer.run.completed")) {
    return 3;
  }
  if (eventTypes.has("writer.token")) {
    return 2;
  }
  if (eventTypes.has("writer.tool.started") || eventTypes.has("writer.tool.completed")) {
    return 1;
  }
  return 0;
}

/** Count of completed writer tool calls observed in the stream. */
export function writerToolCompletedCount(events: readonly WriterRunEvent[]): number {
  return events.filter((event) => event.event_type === "writer.tool.completed").length;
}

/**
 * Terminal writer event types per the shared writer-public-event contract. A run
 * ends in exactly one of these; a closed connection alone is not terminal.
 */
const TERMINAL_WRITER_EVENT_TYPES = new Set([
  "writer.run.completed",
  "writer.run.failed",
  "writer.run.cancelled",
]);

/**
 * True once a terminal writer event (completed, failed, or cancelled) has been
 * observed in the stream. A closed connection alone never implies terminal — callers
 * should combine this with the authoritative run status before declaring an outcome.
 */
export function writerStreamReachedTerminal(events: readonly WriterRunEvent[]): boolean {
  return events.some((event) => TERMINAL_WRITER_EVENT_TYPES.has(event.event_type));
}

/** The most recently saved candidate draft id, or "" when none has been observed. */
export function latestDraftId(events: readonly WriterRunEvent[]): string {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.event_type !== "writer.draft.saved" && event.event_type !== "writer.run.completed") {
      continue;
    }
    const draftId = stringValue(event.payload, "draft_id");
    if (draftId) {
      return draftId;
    }
  }
  return "";
}

function stringValue(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}
