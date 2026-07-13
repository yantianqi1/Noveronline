import type { WriterRunEvent, WriterRunEventsSummary } from "./api";

/**
 * Pending selection revision parsed from writer.revision.proposed workflow events.
 * baseText / proposedText are full-block strings so the inline hunk UI can diff them.
 */
export type PendingRevision = {
  blockId: string;
  baseText: string;
  proposedText: string;
  selectionText: string;
  proposedSelectionText: string;
  selectionStart: number;
  selectionEnd: number;
  expectedVersion?: number;
  instruction?: string;
  eventId?: string;
};

export function applySelectionRevision(
  content: string,
  selectionStart: number,
  selectionEnd: number,
  proposedSelectionText: string,
): string {
  const text = String(content ?? "");
  const start = clampIndex(selectionStart, text.length);
  const end = clampIndex(Math.max(selectionStart, selectionEnd), text.length);
  return text.slice(0, start) + String(proposedSelectionText ?? "") + text.slice(end);
}

/**
 * Latest writer.revision.proposed for the selected block, merged onto current server content.
 * Returns null when the event is missing, targets another block, or produces no change.
 */
export function pendingRevisionFromWriterEvents(
  events: WriterRunEventsSummary | null | undefined,
  options: {
    blockId: string;
    contentText: string;
    expectedVersion?: number;
  },
): PendingRevision | null {
  if (!events || events.ok !== true || !options.blockId) return null;
  for (let index = events.items.length - 1; index >= 0; index -= 1) {
    const event = events.items[index];
    if (!event || event.event_type !== "writer.revision.proposed") continue;
    const parsed = pendingRevisionFromEvent(event, options);
    if (parsed) return parsed;
  }
  return null;
}

export function pendingRevisionFromEvent(
  event: WriterRunEvent,
  options: {
    blockId: string;
    contentText: string;
    expectedVersion?: number;
  },
): PendingRevision | null {
  if (event.event_type !== "writer.revision.proposed") return null;
  const payload = event.payload ?? {};
  const blockId = stringField(payload, "block_id");
  if (!blockId || blockId !== options.blockId) return null;

  const proposedSelectionText = stringField(payload, "proposed_text");
  if (!proposedSelectionText) return null;

  const content = String(options.contentText ?? "");
  const selectionText = stringField(payload, "selection_text");
  const start = numberField(payload, "selection_start");
  const end = numberField(payload, "selection_end");

  let selectionStart = start ?? -1;
  let selectionEnd = end ?? -1;

  if (selectionStart < 0 || selectionEnd < selectionStart) {
    const located = selectionText ? content.indexOf(selectionText) : -1;
    if (located < 0) return null;
    selectionStart = located;
    selectionEnd = located + selectionText.length;
  }

  const baseSlice = content.slice(selectionStart, selectionEnd);
  if (selectionText && baseSlice !== selectionText) {
    // Server content drifted from the selection the model revised — still offer
    // the proposal against the recorded offsets when they are in range.
    if (selectionStart > content.length || selectionEnd > content.length) {
      return null;
    }
  }

  const proposedText = applySelectionRevision(content, selectionStart, selectionEnd, proposedSelectionText);
  if (proposedText === content) return null;

  const expectedFromEvent = numberField(payload, "expected_version");
  return {
    blockId,
    baseText: content,
    proposedText,
    selectionText: selectionText || baseSlice,
    proposedSelectionText,
    selectionStart,
    selectionEnd,
    expectedVersion: options.expectedVersion ?? expectedFromEvent,
    instruction: stringField(payload, "instruction") || undefined,
    eventId: event.event_id,
  };
}

function stringField(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function numberField(payload: Record<string, unknown>, key: string): number | undefined {
  const value = payload[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

function clampIndex(value: number, length: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > length) return length;
  return Math.floor(value);
}
