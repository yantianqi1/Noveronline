import type {
  WorldlinePreparationAgentRef,
  WorldlinePreparationSourceRef,
  WorldlineSessionRecord,
  WorldlineSessionsSummary,
} from "./api";

const sourceKinds = new Set<WorldlinePreparationSourceRef["source_kind"]>([
  "asset",
  "entity",
  "saved_path",
  "worldline_event",
]);

export type JourneyTypedRef = WorldlinePreparationSourceRef;

export function encodeJourneyRef(ref: JourneyTypedRef) {
  return `${ref.source_kind}:${ref.source_id}`;
}

export function parseJourneyRef(value: string): JourneyTypedRef | null {
  const separator = value.indexOf(":");
  if (separator <= 0) return null;
  const sourceKind = value.slice(0, separator) as JourneyTypedRef["source_kind"];
  const sourceId = value.slice(separator + 1).trim();
  if (!sourceKinds.has(sourceKind) || !sourceId) return null;
  return { source_kind: sourceKind, source_id: sourceId };
}

export function journeyRefsFromFormData(formData: FormData, key: string) {
  const refs = formData
    .getAll(key)
    .filter((value): value is string => typeof value === "string")
    .map(parseJourneyRef)
    .filter((value): value is JourneyTypedRef => value !== null);
  return Array.from(new Map(refs.map((ref) => [encodeJourneyRef(ref), ref])).values());
}

export function agentRefsFromFormData(formData: FormData, key: string) {
  return journeyRefsFromFormData(formData, key).filter(
    (ref): ref is WorldlinePreparationAgentRef =>
      ref.source_kind === "asset" || ref.source_kind === "entity",
  );
}

export function selectCurrentWorldSession(
  sessions: WorldlineSessionsSummary,
  requestedSessionId: string,
): WorldlineSessionRecord | undefined {
  if (!sessions.ok) return undefined;
  const active = sessions.items.filter((session) => session.lifecycle === "active");
  return active.find((session) => session.session_id === requestedSessionId) ?? active[0];
}

export function parseCharacterAnchorRef(value: string) {
  const ref = parseJourneyRef(value);
  if (ref) {
    const anchorType = ref.source_kind === "entity" ? "graph_node" : ref.source_kind;
    return { anchorType, anchorId: ref.source_id };
  }
  const separator = value.indexOf(":");
  if (separator <= 0) return { anchorType: "", anchorId: "" };
  const anchorType = value.slice(0, separator);
  const anchorId = value.slice(separator + 1).trim();
  return { anchorType, anchorId };
}

export function positiveBoundedInteger(value: FormDataEntryValue | null, fallback: number, max: number) {
  const parsed = typeof value === "string" ? Number.parseInt(value, 10) : Number.NaN;
  return Number.isInteger(parsed) && parsed > 0 && parsed <= max ? parsed : fallback;
}
