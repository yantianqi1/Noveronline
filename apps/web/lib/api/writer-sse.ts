import type { WriterEvent } from "./writer-types";

/** Parse one complete SSE frame emitted by the Go writer event endpoint. */
export function parseWriterEventSSEFrame(frame: string): WriterEvent | null {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart())
    .join("\n");
  if (!data) return null;
  try {
    const event = JSON.parse(data) as WriterEvent;
    return typeof event.event_id === "string" && typeof event.event_type === "string" ? event : null;
  } catch {
    return null;
  }
}
