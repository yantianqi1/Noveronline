/**
 * Encode / decode local manuscript drafts carried across OPTIMISTIC_CONFLICT redirects.
 *
 * Prefer compact base64url so Unicode prose survives query-string round-trips without
 * double-encoding surprises. Falls back to plain text for short legacy values.
 */

const PREFIX = "b64:";

export function encodeLocalDraft(text: string): string {
  const value = String(text ?? "");
  if (!value) return "";
  try {
    return `${PREFIX}${Buffer.from(value, "utf8").toString("base64url")}`;
  } catch {
    return value;
  }
}

export function decodeLocalDraft(encoded: string | null | undefined): string {
  const value = String(encoded ?? "");
  if (!value || value === "session") return "";
  if (!value.startsWith(PREFIX)) return value;
  try {
    return Buffer.from(value.slice(PREFIX.length), "base64url").toString("utf8");
  } catch {
    return "";
  }
}

export function localDraftStorageKey(blockId: string): string {
  return `writer-local-draft:${blockId}`;
}
