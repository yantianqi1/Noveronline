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
 * A structural scene within a chapter. Scenes carry planning metadata only
 * (brief/outline via the private read) — the prose itself stays on manuscript
 * blocks (CONN-001). `optimistic_version` is the lock for mutations.
 */
export type Scene = {
  scene_id: string;
  chapter_id: string;
  project_id: string;
  title: string;
  status: string;
  scene_order: number;
  optimistic_version: number;
  created_at: string;
  updated_at: string;
};

/** A scene with its private planning fields (single-scene private read). */
export type SceneDetail = Scene & {
  private?: { brief: string; outline: string; content_text: string } | null;
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

/** Scenes list envelope — writerworkspace mount wraps in `data`. */
export type SceneListResponse = { data: Scene[] | null };

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

/**
 * A candidate draft the writer run saved. `content_text` comes back only when
 * requested with `?include=content`; `status` flips to "adopted" once the
 * author has adopted it into the manuscript.
 */
export type WriterDraft = {
  draft_id: string;
  project_id: string;
  run_id?: string;
  chapter_id?: string;
  status: string;
  word_count?: number;
  content_text?: string;
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

/**
 * 审校 (review) view types. A draft-review issue is a single reviewer finding
 * against one draft. `severity` ranks impact; `status` tracks the author's
 * triage decision. Issues have no manuscript-block anchor, so "在稿件中定位"
 * degrades to opening the draft's chapter. The PATCH optimistic-lock `version`
 * is the issue's `updated_at` timestamp string.
 */
export type DraftReviewIssue = {
  issue_id: string;
  severity: "low" | "medium" | "high" | "critical" | string;
  category?: string;
  summary: string;
  suggestion?: string;
  status: "open" | "accepted" | "dismissed" | "resolved" | string;
  created_at?: string;
  updated_at?: string;
};

/** An issue plus the draft/chapter it belongs to (from the project queue). */
export type ProjectReviewIssue = DraftReviewIssue & {
  draft_id: string;
  chapter_id?: string;
};

/**
 * One queue bucket: a draft that has issues in the requested status, carrying
 * its chapter + the run's instruction so the queue reads "which chapter / what
 * prompt" without a second round-trip.
 */
export type ProjectDraftReviewBucket = {
  draft_id: string;
  chapter_id?: string;
  instruction?: string;
  word_count: number;
  open_count: number;
  issues: ProjectReviewIssue[];
};

export type ProjectDraftReviewQueue = {
  project_id: string;
  items: ProjectDraftReviewBucket[];
};

export type ProjectDraftReviewQueueResponse = { data: ProjectDraftReviewQueue };

// ── 工具 Tools view types ────────────────────────────────────────────────────

/** One manuscript export job (导出手稿). Generated async; poll `status`. */
export type ManuscriptExport = {
  export_id: string;
  project_id: string;
  format: "txt" | "docx" | "pdf" | "epub" | string;
  status: "queued" | "generating" | "completed" | "failed" | string;
  artifact_sha256?: string;
  artifact_size_bytes?: number;
  block_count: number;
  error_code?: string;
  created_at?: string;
  completed_at?: string;
  updated_at?: string;
};

/** One forbidden-lexicon entry (违禁词库). */
export type ForbiddenEntry = {
  lexicon_entry_id: string;
  project_id: string;
  term: string;
  category?: string;
  severity?: "low" | "medium" | "high" | string;
  replacement_guidance?: string;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
};

/** One writer preset (写作预设). `settings` is a JSON string of knob values. */
export type WriterPreset = {
  writer_preset_id: string;
  scope: "project" | "tenant" | string;
  project_id?: string;
  name: string;
  description?: string;
  settings?: string;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
};

/** One dedup candidate (重复检测). Triage is accept/reject, not a PATCH. */
export type DedupPattern = {
  pattern_id: string;
  project_id: string;
  pattern_text: string;
  normalized_pattern?: string;
  pattern_kind?: string;
  lifecycle: "candidate" | "accepted" | "rejected" | string;
  enabled: boolean;
  occurrence_count: number;
  created_at?: string;
  updated_at?: string;
};
