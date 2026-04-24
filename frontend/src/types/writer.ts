export interface Chapter {
  id: string;
  project_id: string;
  title: string;
  outline: string;
  order_index: number;
  scene_count?: number;
  word_count?: number;
  created_at: string;
  updated_at: string;
}

export interface Scene {
  id: string;
  chapter_id: string;
  project_id: string;
  title: string;
  summary: string;
  pov: string;
  setting: string;
  characters: string;
  notes: string;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface Preset {
  id: string;
  project_id: string;
  name: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ManuscriptBlock {
  id: string;
  project_id: string;
  chapter_id: string;
  scene_id?: string;
  content: string;
  block_type: string;
  order_index: number;
  tags: string[];
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface OutlineVersion {
  id: string;
  chapter_id: string;
  project_id: string;
  outline_text: string;
  label?: string;
  created_at: string;
}

export interface WriterEvent {
  type: string;
  [key: string]: unknown;
}

export interface ContinuationContext {
  fragments: ContinuationFragment[];
  total_tokens: number;
  budget: number;
}

export interface ContinuationFragment {
  source: string;
  content: string;
  token_count: number;
}

/* ---------- Tool render protocol (W-2 §2) ---------- */

export type ToolRenderType =
  | "scene_proposal"
  | "chapter_structure_proposal"
  | "entity_card"
  | "prose_diff"
  | "word_budget"
  | "thread_board"
  | "relation_subgraph"
  | "scene_timeline"
  | "relationship_proposal";

export interface ToolRenderAction {
  label: string;
  /** Debug hint only — the frontend dispatches by render.type to API clients. */
  endpoint?: string;
  kind?: string;
  payload_ref?: string;
  confirm?: string;
  variant?: "primary" | "secondary" | "destructive" | "ghost";
}

export interface ToolRenderBase<T extends ToolRenderType, D> {
  version: 1;
  type: T;
  data: D;
  actions: ToolRenderAction[];
  tool_call_id?: string | null;
}

/* ---- Per-type `data` shapes ---- */

export interface SceneProposalData {
  chapter_id: string;
  chapter_order: number;
  scene_order: number;
  mode: "insert" | "replace";
  replace_scene_id?: string;
  insert_after_scene_order?: number;
  title: string;
  summary: string;
  pov: string;
  setting?: string;
  characters?: string[];
  key_events?: string[];
  estimated_word_count?: number;
  target_word_count?: number;
  rationale?: string;
  reason?: string;
  related_entities?: string[];
  related_threads?: string[];
}

export interface ChapterStructureProposalChapter {
  chapter_order: number;
  title: string;
  summary: string;
  hook?: string;
  word_target: number;
  pov_character?: string;
  key_threads?: string[];
}

export interface ChapterStructureProposalData {
  plan_id?: string;
  start_chapter_order: number;
  chapters: ChapterStructureProposalChapter[];
  overall_arc?: string;
  rationale?: string;
}

export interface EntityCardRelation {
  other_entity_id: string;
  other_name: string;
  relation_type: string;
  trust_level?: number;
  description?: string;
}

export interface EntityCardEvent {
  event_id: string;
  chapter_order?: number;
  event_type: string;
  summary: string;
}

export interface EntityCardMemory {
  memory_id: string;
  salience: number;
  canon: boolean;
  content: string;
}

export type EntityCardSection =
  | "overview"
  | "profile"
  | "relations"
  | "events"
  | "memories";

export interface EntityCardData {
  mode: "view" | "propose";
  entity_id: string | null;
  name: string;
  entity_type: "character" | "organization" | "item" | "location" | "skill";
  aliases?: string[];
  tags?: string[];
  summary: string;
  section: EntityCardSection;
  overview?: {
    core_drive?: string;
    surface_mask?: string;
    hidden_tension?: string;
    current_objective?: string;
  };
  profile?: {
    deep_profile_md?: string;
    values_text?: string;
    fears_text?: string;
    voice_style?: string;
    decision_pattern?: string;
  };
  relations?: EntityCardRelation[];
  events?: EntityCardEvent[];
  memories?: EntityCardMemory[];
  next_cursor?: string;
}

export interface ProseDiffHunk {
  hunk_id: string;
  original: string;
  replacement: string;
  reason?: string;
  severity?: "high" | "medium" | "low";
  category?: string;
  location_hint?: string;
}

export interface ProseDiffData {
  scope: "manuscript_block" | "scene";
  target_id: string;
  chapter_label?: string;
  hunks: ProseDiffHunk[];
  word_delta?: number;
  source: "reviewer" | "rewrite_span" | "diff_prose" | "splice_block";
}

export interface WordBudgetBlock {
  block_id: string;
  block_order: number;
  word_count: number;
  preview?: string;
}

export interface WordBudgetData {
  chapter_id: string;
  chapter_order: number;
  chapter_title?: string;
  target: number;
  total: number;
  diff: number;
  tolerance_pct?: number;
  blocks: WordBudgetBlock[];
  status: "under" | "on_target" | "over";
}

export interface ThreadBoardThread {
  thread_id: string;
  thread_key: string;
  status: "open" | "progressed" | "resolved";
  detail: string;
  opened_chapter?: number;
  last_touched_chapter?: number;
  resolved_chapter?: number;
  resolution_detail?: string;
  related_entities?: string[];
  age_chapters?: number;
}

export interface ThreadBoardData {
  scope: "project" | "up_to_chapter";
  up_to_chapter_order?: number;
  threads: ThreadBoardThread[];
  staleness_threshold?: number;
}

export interface RelationSubgraphNode {
  entity_id: string;
  name: string;
  entity_type: "character" | "organization" | "item" | "location" | "skill";
  tags?: string[];
  is_focus: boolean;
}

export interface RelationSubgraphEdge {
  edge_id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  trust_level?: number;
  is_candidate: boolean;
  description?: string;
}

export interface RelationSubgraphData {
  focus_entity_ids: string[];
  depth: 1 | 2;
  nodes: RelationSubgraphNode[];
  edges: RelationSubgraphEdge[];
  stats: { node_count: number; edge_count: number };
}

export interface SceneTimelineEvent {
  event_id: string;
  axis_value: number;
  label: string;
  subtitle?: string;
  event_type?:
    | "scene"
    | "action"
    | "state_change"
    | "knowledge"
    | "emotional"
    | "branch_step";
  highlight?: boolean;
  related_entity_id?: string;
  related_thread_key?: string;
}

export interface SceneTimelineData {
  mode: "chapter" | "character" | "branch";
  title: string;
  axis: "scene_order" | "chapter_order" | "step";
  events: SceneTimelineEvent[];
}

export interface RelationshipProposalData {
  entity_a: string;
  entity_b: string;
  entity_a_id?: string;
  entity_b_id?: string;
  relation_type: string;
  description: string;
  trust_level?: number;
  power_dynamic?: string;
  conflict_trigger?: string;
  evidence_snippet?: string;
  source_scene_ids?: string[];
}

export type ToolRenderPayload =
  | ToolRenderBase<"scene_proposal", SceneProposalData>
  | ToolRenderBase<"chapter_structure_proposal", ChapterStructureProposalData>
  | ToolRenderBase<"entity_card", EntityCardData>
  | ToolRenderBase<"prose_diff", ProseDiffData>
  | ToolRenderBase<"word_budget", WordBudgetData>
  | ToolRenderBase<"thread_board", ThreadBoardData>
  | ToolRenderBase<"relation_subgraph", RelationSubgraphData>
  | ToolRenderBase<"scene_timeline", SceneTimelineData>
  | ToolRenderBase<"relationship_proposal", RelationshipProposalData>;

export function isRender<T extends ToolRenderType>(
  payload: unknown,
  type: T,
): payload is Extract<ToolRenderPayload, { type: T }> {
  return (
    !!payload &&
    typeof payload === "object" &&
    (payload as { type?: unknown }).type === type
  );
}
