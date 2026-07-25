/**
 * Writer workbench domain types — mirrors the Go control plane's chapter and
 * manuscript-workspace records. Field names match the API verbatim so the BFF
 * proxy can relay payloads without a mapping layer.
 */

/** A structural chapter (writerworkspace mount — `data`-wrapped list). */
export type Chapter = {
  chapter_id: string;
  project_id: string;
  title: string;
  status: string;
  chapter_order: number;
  optimistic_version: number;
  created_at: string;
  updated_at: string;
};

/**
 * Manuscript block metadata (list view — no body text). The list endpoint
 * never serializes `content_text`; the body is only exposed by the
 * single-block read, keeping prose out of list payloads.
 */
export type ManuscriptBlockMeta = {
  block_id: string;
  project_id: string;
  chapter_id?: string;
  scene_id?: string;
  source_draft_id?: string;
  source_writer_run_id?: string;
  status: string;
  tags: string[];
  block_order: number;
  word_count: number;
  version: number;
  created_at: string;
  updated_at: string;
};

/** A manuscript block with its body (single-block read / mutation result). */
export type ManuscriptBlock = ManuscriptBlockMeta & {
  content_text: string;
};

/** Chapters list envelope — writerworkspace mount wraps in `data`. */
export type ChapterListResponse = { data: Chapter[] | null };

/** Manuscript block list envelope — manuscriptworkspace mount is bare. */
export type BlockListResponse = { blocks: ManuscriptBlockMeta[] | null };

// ── W2: conversation + run + candidate ──────────────────────────────────

/** A persistent conversation thread with the Writer Agent. */
export type WriterThread = {
  thread_id: string;
  project_id: string;
  title?: string;
  status: string;
  updated_at: string;
};

/** One message in the thread. `role` is "user" | "assistant". */
export type WriterMessage = {
  message_id: string;
  thread_id: string;
  role: string;
  body: string;
  run_id?: string;
  sequence: number;
  created_at: string;
  metadata?: Record<string, unknown>;
};

/** A writer run (202 on start; the detail read adds live status). */
export type WriterRun = {
  run_id: string;
  trace_id: string;
  project_id: string;
  mode: string;
  instruction: string;
  status: string;
};

/**
 * One event in a run's stream. `sequence` is the global order; `event_id` is
 * the resume cursor. The events endpoint pages at 100 and returns no cursor,
 * so the client resumes with `?after_event_id=<last event_id>` until a page
 * comes back short.
 */
export type WriterEvent = {
  event_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at?: string;
};

/** The result of adopting a candidate draft into the manuscript. */
export type DraftAdoption = {
  draft_id: string;
  block_id: string;
  project_id: string;
  status: string;
  chapter_id?: string;
  scene_id?: string;
  block_order: number;
};

export type ThreadListResponse = { threads?: WriterThread[] | null; data?: WriterThread[] | null };
export type MessageListResponse = { messages?: WriterMessage[] | null };
export type EventListResponse = { items?: WriterEvent[] | null };
