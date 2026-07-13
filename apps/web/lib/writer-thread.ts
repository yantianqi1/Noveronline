/**
 * Pure helpers for persistent writer thread messages.
 * Order by created_at then sequence; never invent success from missing data.
 */

export type WriterThreadMessageRole = "user" | "agent" | "system" | "approval";

export type WriterThreadMessage = {
  message_id: string;
  thread_id: string;
  role: WriterThreadMessageRole;
  body: string;
  run_id?: string;
  created_at: string;
  sequence: number;
  metadata?: Record<string, unknown>;
};

export type WriterThread = {
  thread_id: string;
  project_id: string;
  title?: string;
  updated_at: string;
  messages: WriterThreadMessage[];
};

/** Stable chronological order for thread rendering. */
export function sortThreadMessages(messages: readonly WriterThreadMessage[]): WriterThreadMessage[] {
  return [...messages].sort((left, right) => {
    if (left.sequence !== right.sequence) {
      return left.sequence - right.sequence;
    }
    return left.created_at.localeCompare(right.created_at) || left.message_id.localeCompare(right.message_id);
  });
}

/** Merge server page + newly posted optimistic messages by message_id. */
export function mergeThreadMessages(
  known: readonly WriterThreadMessage[],
  incoming: readonly WriterThreadMessage[],
): WriterThreadMessage[] {
  const byId = new Map<string, WriterThreadMessage>();
  for (const message of known) {
    byId.set(message.message_id, message);
  }
  for (const message of incoming) {
    byId.set(message.message_id, message);
  }
  return sortThreadMessages([...byId.values()]);
}

export function latestThreadMessage(messages: readonly WriterThreadMessage[]): WriterThreadMessage | null {
  const sorted = sortThreadMessages(messages);
  return sorted[sorted.length - 1] ?? null;
}
