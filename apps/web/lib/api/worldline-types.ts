/**
 * Wire types mirroring the Go control plane's worldline package
 * (apps/api/internal/worldline/worldline.go). Field names are snake_case as
 * they appear on the wire. Worldline is the 单世界推演 (single-world
 * simulation) domain: prepare a cast, then step the world forward, inject and
 * lock variables, and adopt candidate events into the canon timeline.
 *
 * Safety contract:推演/自动演化只产出「候选」(lifecycle/status candidate);
 * only an explicit adopt call turns an event into canon. The UI never invents
 * events — it renders what these records carry and surfaces coded errors when
 * the backend is unconfigured.
 */

export type WorldlineSession = {
  session_id: string;
  run_id: string;
  project_id: string;
  status: string;
  lifecycle: string;
  goal_summary: string;
  anchor_path_id: string;
  /**
   * The domain step anchor (MAX(worldline_events.step) for this session) — the
   * single public "第 X 步". The orchestration timeline `sequence` counts
   * bookkeeping rows too (adoptions bump it without stepping the world), so the
   * banner/cards must never read step from it.
   */
  current_step: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type WorldlineSessionRun = {
  run_id: string;
  project_id: string;
  workflow_type: string;
  status: string;
};

export type WorldlinePreparationRef = {
  source_kind: string;
  source_id: string;
};

/**
 * A goal-driven 整备 run (worldline_goal_start). The Pi cast planner decomposes
 * the author's goal against the asset library, commits a cast, prepares each
 * agent, and only then admits the worldline session — the status ladder is
 * queued → casting → preparing → starting → ready, or failed at any point.
 */
export type WorldlineGoalStart = {
  run_id: string;
  trace_id?: string;
  project_id: string;
  workflow_type: string;
  status: string;
  goal?: string;
  anchor_path_id?: string;
  agent_refs?: WorldlinePreparationRef[];
  source_refs?: WorldlinePreparationRef[];
  rationale?: string;
  prepare_id?: string;
  session_id?: string;
  error_code?: string;
  error_message?: string;
  created_at?: string;
  updated_at?: string;
  result?: Record<string, unknown>;
};

export type WorldlineStepRun = {
  run_id: string;
  project_id: string;
  session_id: string;
  workflow_type: string;
  status: string;
};

/** A canon (timeline) event — already confirmed into the world's history. */
export type WorldlineTimelineEvent = {
  event_id: string;
  session_id: string;
  run_id: string;
  project_id: string;
  event_type: string;
  sequence: number;
  status: string;
  lifecycle: string;
  title: string;
  summary: string;
  kind: string;
  /** For adoption records: the canon domain event this orchestration step adopted. */
  event_ref_id?: string;
  adopted_title?: string;
  adopted_summary?: string;
  created_at: string;
};

/** A full event record — candidate or canon, with adoption metadata. */
export type WorldlineEvent = {
  event_id: string;
  session_id: string;
  project_id: string;
  step: number;
  title: string;
  summary: string;
  kind: string;
  status: string;
  lifecycle: string;
  /** Orchestration event_type for timeline rows (workflow.* markers vs worldline.* records). */
  event_type?: string;
  confidence: string;
  involved_agent_ids: string[];
  state_changes: Record<string, unknown>;
  source_run_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type WorldlinePreparation = {
  prepare_id: string;
  run_id: string;
  project_id: string;
  workflow_type: string;
  status: string;
  lifecycle: string;
  goal_summary: string;
  anchor_path_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type WorldlinePreparedAgent = {
  agent_id: string;
  prepare_id: string;
  project_id: string;
  display_name: string;
  role: string;
  status: string;
  source_asset_id: string;
  summary: string;
  created_at: string;
  updated_at: string;
};

export type WorldlineVariable = {
  variable_id: string;
  session_id: string;
  project_id: string;
  name: string;
  description: string;
  impact_axis: string;
  locked: boolean;
  source: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type WorldlineSavedPath = {
  path_id: string;
  session_id: string;
  project_id: string;
  title: string;
  summary: string;
  lifecycle: string;
  selected_event_ids: string[];
  writer_instruction: string;
  created_at: string;
  updated_at: string;
};

/** Status/lifecycle literals used across worldline records. */
export const WORLDLINE_CANDIDATE = "candidate";
export const WORLDLINE_CANON = "canon";
