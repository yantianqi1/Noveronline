export interface ArchiveEntry {
  archive_id: string;
  entity_name: string;
  entity_type: string;
  importance_tier?: string;
  project_id: string;
  project_name?: string;
  entity_uuid?: string;
  agent_kind?: string;
  recommended_importance_tier?: string;
  selected_importance_tier?: string;
  template_key?: string;
  template_version?: string;
  template_sections?: string[];
  template_payload?: Record<string, unknown>;
  template_metadata?: Record<string, unknown>;
  entity_role?: string;
  core_drive?: string;
  surface_mask?: string;
  hidden_tension?: string;
  relationship_summary?: string;
  agent_behavior_hint?: string;
  human_ai_relation_tag?: string;
  can_act_as_agent?: boolean;
  notable_risks?: string[];
  synced_at?: string;
  [key: string]: unknown;
}

export interface ArchiveMemory {
  id: string;
  archive_id: string;
  subject: string;
  normalized_subject: string;
  content: string;
  memory_type: string;
  layer: string;  // canon | candidate | experiment
  status: string;
  source: string;
  created_at: string;
}

export interface MemoryTimeline {
  subject: string;
  events: MemoryTimelineEvent[];
}

export interface MemoryTimelineEvent {
  id: string;
  event_type: string;
  content: string;
  timestamp: string;
  source: string;
}
