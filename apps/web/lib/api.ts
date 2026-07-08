const DEFAULT_API_BASE_URL = "http://127.0.0.1:8080";

export type ApiContext = {
  tenantId: string;
  actorUserId?: string;
  sessionCookie?: string;
};

export type ApiFailure = {
  ok: false;
  code: string;
  message: string;
  request_id: string;
};

export type TenantMembershipSummary = {
  tenant_id: string;
  name: string;
  role: string;
  status: string;
};

export type ProjectMembershipSummary = {
  tenant_id: string;
  project_id: string;
  name: string;
  role: string;
  status: string;
};

export type CurrentUserRecord = {
  user_id: string;
  email: string;
  display_name: string;
  avatar_url: string;
  active_tenants: TenantMembershipSummary[];
  active_projects: ProjectMembershipSummary[];
};

export type CurrentUserSummary =
  | ({
      ok: true;
    } & CurrentUserRecord)
  | ApiFailure;

export type SessionRevokeSummary =
  | {
      ok: true;
    }
  | ApiFailure;

export type SessionCSRFTokenSummary =
  | {
      ok: true;
      csrf_token: string;
    }
  | ApiFailure;

export type WriterRunSummary =
  | {
      ok: true;
      run_id: string;
      trace_id: string;
      project_id: string;
      status: string;
    }
  | ApiFailure;

export type WriterRunEvent = {
  event_id: string;
  run_id: string;
  project_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type WriterRunEventsSummary =
  | {
      ok: true;
      run_id: string;
      after_event_id: string;
      items: WriterRunEvent[];
    }
  | ApiFailure;

export type ManuscriptBlockMetadata = {
  block_id: string;
  chapter_id: string;
  source_draft_id: string;
  block_order: number;
  status: string;
  word_count: number;
  created_at: string;
  updated_at: string;
};

export type ProjectManuscriptSummary =
  | {
      ok: true;
      project_id: string;
      blocks: ManuscriptBlockMetadata[];
    }
  | ApiFailure;

export type ManuscriptExportManifestBlock = {
  block_id: string;
  block_order: number;
  word_count: number;
};

export type ProjectManuscriptExportManifestSummary =
  | {
      ok: true;
      project_id: string;
      format: string;
      status: string;
      block_count: number;
      total_word_count: number;
      generated_at: string;
      blocks: ManuscriptExportManifestBlock[];
    }
  | ApiFailure;

export type WorkflowRunSummary =
  | {
      ok: true;
      run_id: string;
      workflow_type: string;
      project_id: string;
      status: string;
      progress: number;
      message: string;
      error_code: string;
      error_message: string;
      created_at: string;
      updated_at: string;
    }
  | ApiFailure;

export type WorkflowRunEvent = {
  event_id: string;
  run_id: string;
  project_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type WorkflowRunEventsSummary =
  | {
      ok: true;
      run_id: string;
      after_event_id: string;
      items: WorkflowRunEvent[];
    }
  | ApiFailure;

export type SourceFileRecord = {
  file_id: string;
  upload_id: string;
  project_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  purpose: string;
  parse_status: string;
  created_at: string;
};

export type SourceFilesSummary =
  | {
      ok: true;
      items: SourceFileRecord[];
    }
  | ApiFailure;

export type SourceFileSummary =
  | ({
      ok: true;
    } & SourceFileRecord)
  | ApiFailure;

export type SourceFileObjectUploadSummary =
  | {
      ok: true;
      upload_id: string;
      status: string;
    }
  | ApiFailure;

export type ProjectOverviewRecord = {
  project_id: string;
  status: string;
  source_file_count: number;
  seed_run_count: number;
  active_workflow_run_id: string;
  active_workflow_type: string;
  active_workflow_status: string;
  readiness_snapshot_id: string;
  readiness_run_id: string;
  ready_asset_count: number;
  ready_entity_count: number;
  ready_relationship_count: number;
  ready_world_rule_count: number;
  asset_count: number;
  graph_node_count: number;
  graph_edge_count: number;
  worldline_session_count: number;
  worldline_event_count: number;
  character_interaction_count: number;
  writer_run_count: number;
  llm_activity_count: number;
  llm_token_count: number;
  llm_enabled_channel_count: number;
  llm_bound_module_count: number;
  llm_missing_core_module_count: number;
  llm_sync_ok_channel_count: number;
  llm_sync_failed_channel_count: number;
  llm_sync_pending_channel_count: number;
  llm_latest_sync_at: string;
  latest_failed_workflow_run_id: string;
  latest_failed_workflow_type: string;
  latest_failed_workflow_error_code: string;
  latest_failed_workflow_updated_at: string;
  updated_at: string;
};

export type ProjectOverviewSummary =
  | ({
      ok: true;
    } & ProjectOverviewRecord)
  | ApiFailure;

export type ProjectReadinessSnapshot = {
  project_readiness_snapshot_id: string;
  project_id: string;
  run_id: string;
  ready_asset_count: number;
  ready_entity_count: number;
  ready_relationship_count: number;
  ready_world_rule_count: number;
  created_at: string;
  updated_at: string;
};

export type ProjectReadinessSummary =
  | ({
      ok: true;
    } & ProjectReadinessSnapshot)
  | ApiFailure;

export type SeedRunStartSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type SeedRunsSummary =
  | {
      ok: true;
      items: WorkflowRunSummary[];
    }
  | ApiFailure;

export type WorkflowControlSummary =
  | {
      ok: true;
      run_id: string;
      status: string;
    }
  | ApiFailure;

export type AgentTraceEvent = {
  event_id: string;
  trace_id: string;
  event_order: number;
  event_type: string;
  payload: Record<string, unknown>;
  redaction_level: string;
  created_at: string;
};

export type AgentTraceEventsSummary =
  | {
      ok: true;
      project_id: string;
      trace_id: string;
      include_full: boolean;
      items: AgentTraceEvent[];
    }
  | ApiFailure;

export type LLMModuleResolutionSummary =
  | {
      ok: true;
      module_key: string;
      channel_id: string;
      model_id: string;
      provider: string;
      base_url: string;
      supports_tools: boolean;
      supports_json: boolean;
      settings: Record<string, unknown>;
    }
  | ApiFailure;

export type LLMModuleBindingRecord = {
  module_key: string;
  scope: string;
  channel_id: string;
  channel_name: string;
  model_id: string;
  provider: string;
  base_url: string;
  supports_tools: boolean;
  supports_json: boolean;
  settings: Record<string, unknown>;
  updated_at: string;
};

export type LLMModuleRecord = {
  module_key: string;
  group: string;
  label: string;
  description: string;
};

export type LLMModulesSummary =
  | {
      ok: true;
      items: LLMModuleRecord[];
    }
  | ApiFailure;

export type LLMModuleBindingsSummary =
  | {
      ok: true;
      items: LLMModuleBindingRecord[];
    }
  | ApiFailure;

export type LLMModuleBindingSummary =
  | ({
      ok: true;
    } & LLMModuleBindingRecord)
  | ApiFailure;

export type LLMChannelRecord = {
  channel_id: string;
  name: string;
  provider: string;
  base_url: string;
  max_concurrency: number;
  enabled: boolean;
  last_sync_at: string;
  last_sync_status: string;
  scope: string;
  created_at: string;
  updated_at: string;
};

export type LLMChannelsSummary =
  | {
      ok: true;
      items: LLMChannelRecord[];
    }
  | ApiFailure;

export type LLMChannelSummary =
  | ({
      ok: true;
    } & LLMChannelRecord)
  | ApiFailure;

export type LLMModelRecord = {
  model_id: string;
  owned_by: string;
  context_window: number;
  supports_tools: boolean;
  supports_json: boolean;
  input_cost: number;
  output_cost: number;
  created_at: string;
  updated_at: string;
};

export type LLMChannelModelsSummary =
  | {
      ok: true;
      items: LLMModelRecord[];
    }
  | ApiFailure;

export type LLMModelSyncSummary =
  | {
      ok: true;
      channel: LLMChannelRecord;
      models: LLMModelRecord[];
    }
  | ApiFailure;

export type LLMSettingsSummary =
  | {
      ok: true;
      modules: LLMModuleRecord[];
      channels: LLMChannelRecord[];
      tenant_bindings: LLMModuleBindingRecord[];
    }
  | ApiFailure;

export type LLMActivityRecord = {
  activity_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  cost_estimate: number;
  error: Record<string, unknown> | null;
  created_at: string;
};

export type LLMActivitySummary =
  | {
      ok: true;
      items: LLMActivityRecord[];
    }
  | ApiFailure;

export type LLMUsageRecord = {
  usage_type: string;
  quantity: number;
  unit: string;
  module_key: string;
  run_id: string;
};

export type LLMUsageSummary =
  | {
      ok: true;
      items: LLMUsageRecord[];
    }
  | ApiFailure;

export type AssetRecord = {
  asset_id: string;
  project_id: string;
  scope: string;
  asset_type: string;
  category: string;
  lifecycle: string;
  title: string;
  summary: string;
  source_kind: string;
  source_ref: string;
  enabled: boolean;
  pinned: boolean;
  tags: string[];
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AssetListSummary =
  | {
      ok: true;
      items: AssetRecord[];
    }
  | ApiFailure;

export type WorldlineSavedPathRecord = {
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

export type WorldlineSavedPathsSummary =
  | {
      ok: true;
      items: WorldlineSavedPathRecord[];
    }
  | ApiFailure;

export type WorldlineSavedPathSummary =
  | ({
      ok: true;
    } & WorldlineSavedPathRecord)
  | ApiFailure;

export type WorldlineSessionRecord = {
  session_id: string;
  run_id: string;
  project_id: string;
  status: string;
  lifecycle: string;
  goal_summary: string;
  anchor_path_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type WorldlineSessionsSummary =
  | {
      ok: true;
      items: WorldlineSessionRecord[];
    }
  | ApiFailure;

export type WorldlineSessionSummary =
  | ({
      ok: true;
    } & WorldlineSessionRecord)
  | ApiFailure;

export type WorldlineSessionStartSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type WorldlineStepStartSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      session_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type WorldlineTimelineEventRecord = {
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
  created_at: string;
};

export type WorldlineTimelineSummary =
  | {
      ok: true;
      items: WorldlineTimelineEventRecord[];
    }
  | ApiFailure;

export type WorldlineEventRecord = {
  event_id: string;
  session_id: string;
  project_id: string;
  step: number;
  title: string;
  summary: string;
  kind: string;
  status: string;
  lifecycle: string;
  confidence: string;
  involved_agent_ids: string[];
  state_changes: Record<string, unknown>;
  source_run_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type WorldlineEventsSummary =
  | {
      ok: true;
      items: WorldlineEventRecord[];
    }
  | ApiFailure;

export type WorldlineEventSummary =
  | ({
      ok: true;
    } & WorldlineEventRecord)
  | ApiFailure;

export type WorldlineVariableRecord = {
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

export type WorldlineVariableSummary =
  | ({
      ok: true;
    } & WorldlineVariableRecord)
  | ApiFailure;

export type WorldlinePreparationRecord = {
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

export type WorldlinePreparationSummary =
  | ({
      ok: true;
    } & WorldlinePreparationRecord)
  | ApiFailure;

export type WorldlinePreparedAgentRecord = {
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

export type WorldlinePreparedAgentsSummary =
  | {
      ok: true;
      items: WorldlinePreparedAgentRecord[];
    }
  | ApiFailure;

export type CharacterInteractionRecord = {
  interaction_id: string;
  project_id: string;
  worldline_session_id: string;
  anchor_type: string;
  anchor_id: string;
  pov_agent_id: string;
  mode: string;
  status: string;
  title: string;
  summary: string;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type CreateCharacterInteractionInput = ApiContext & {
  projectId: string;
  worldlineSessionId?: string;
  anchorType?: string;
  anchorId?: string;
  povAgentId?: string;
  mode: string;
  title: string;
  summary?: string;
  metadata?: Record<string, unknown>;
};

export type UpdateCharacterInteractionStatusInput = ApiContext & {
  interactionId: string;
  status: "active" | "saved" | "archived";
};

export type CharacterInteractionTurnRecord = {
  turn_id: string;
  interaction_id: string;
  project_id: string;
  turn_order: number;
  actor_type: string;
  actor_id: string;
  turn_kind: string;
  summary: string;
  action: Record<string, unknown>;
  world_state_delta: Record<string, unknown>;
  trace_id: string;
  created_by: string;
  created_at: string;
};

export type CharacterInteractionsSummary =
  | {
      ok: true;
      items: CharacterInteractionRecord[];
    }
  | ApiFailure;

export type CharacterInteractionSummary =
  | ({
      ok: true;
    } & CharacterInteractionRecord)
  | ApiFailure;

export type CharacterInteractionDetailSummary =
  | ({
      ok: true;
      turns: CharacterInteractionTurnRecord[];
    } & CharacterInteractionRecord)
  | ApiFailure;

export type CharacterInteractionTurnSummary =
  | ({
      ok: true;
    } & CharacterInteractionTurnRecord)
  | ApiFailure;

export type CharacterInteractionTurnsSummary =
  | {
      ok: true;
      items: CharacterInteractionTurnRecord[];
    }
  | ApiFailure;

export type CharacterInteractionEventRecord = {
  event_id: string;
  interaction_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type CharacterInteractionEventsSummary =
  | {
      ok: true;
      interaction_id: string;
      after_event_id: string;
      items: CharacterInteractionEventRecord[];
    }
  | ApiFailure;

export type CharacterInteractionChapterDraftSummary =
  | {
      ok: true;
      interaction_id: string;
      run_id: string;
      trace_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type AssetSummary =
  | ({
      ok: true;
    } & AssetRecord)
  | ApiFailure;

export type AssetFacetBucket = {
  value: string;
  count: number;
};

export type AssetFacetsSummary =
  | {
      ok: true;
      asset_types: AssetFacetBucket[];
      categories: AssetFacetBucket[];
      lifecycles: AssetFacetBucket[];
      sources: AssetFacetBucket[];
      tags: AssetFacetBucket[];
    }
  | ApiFailure;

export type AssetSearchRecord = {
  search_document_id: string;
  source: string;
  source_ref: string;
  project_id: string;
  entity_type: string;
  title: string;
  tags: string[];
  payload: Record<string, unknown>;
  version: AssetSearchVersion;
  collections: AssetSearchCollection[];
  created_at: string;
  updated_at: string;
};

export type AssetSearchVersion = {
  count: number;
  latest_version: number;
  latest_version_id: string;
};

export type AssetSearchCollection = {
  collection_id: string;
  title: string;
  lifecycle: string;
};

export type AssetSearchSummary =
  | {
      ok: true;
      items: AssetSearchRecord[];
    }
  | ApiFailure;

export type ArchiveMemoryRecord = {
  memory_id: string;
  asset_id: string;
  project_id: string;
  memory_type: string;
  status: string;
  summary: string;
  payload: Record<string, unknown>;
  source_kind: string;
  source_ref: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type ArchiveMemoryEventRecord = {
  event_id: string;
  memory_id: string;
  asset_id: string;
  project_id: string;
  event_type: string;
  status: string;
  payload: Record<string, unknown>;
  actor_id: string;
  created_at: string;
};

export type ArchiveMemorySummary =
  | {
      ok: true;
      items: ArchiveMemoryRecord[];
    }
  | ApiFailure;

export type ArchiveMemoryReviewSummary =
  | ({
      ok: true;
    } & ArchiveMemoryRecord)
  | ApiFailure;

export type ArchiveMemoryEventsSummary =
  | {
      ok: true;
      items: ArchiveMemoryEventRecord[];
    }
  | ApiFailure;

export type AssetDeleteSummary =
  | {
      ok: true;
      asset_id: string;
      project_id: string;
      deleted: boolean;
    }
  | ApiFailure;

export type AssetBulkActionSummary =
  | {
      ok: true;
      project_id: string;
      action: string;
      status: string;
      matched_count: number;
      updated_count: number;
    }
  | ApiFailure;

export type AssetIngestionSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type AssetReindexSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type StyleExtractionSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type StoryGraphBuildSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type StoryGraphBondGenerationSummary =
  | {
      ok: true;
      run_id: string;
      project_id: string;
      workflow_type: string;
      status: string;
    }
  | ApiFailure;

export type StoryGraphCurrentSummary =
  | {
      ok: true;
      graph_id: string;
      project_id: string;
      version: number;
      status: string;
      build_run_id: string;
      source_version_hash: string;
      node_count: number;
      edge_count: number;
      created_at: string;
      updated_at: string;
    }
  | ApiFailure;

export type StoryGraphNodeRecord = {
  node_id: string;
  graph_id: string;
  project_id: string;
  node_type: string;
  title: string;
  summary: string;
  lifecycle: string;
  importance: number;
  cluster_id: string;
  attributes: Record<string, unknown>;
  evidence_count: number;
  created_at: string;
  updated_at: string;
};

export type StoryGraphEdgeRecord = {
  edge_id: string;
  graph_id: string;
  project_id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  label: string;
  summary: string;
  weight: number;
  lifecycle: string;
  attributes: Record<string, unknown>;
  evidence_count: number;
  created_at: string;
  updated_at: string;
};

export type StoryGraphViewSummary =
  | {
      ok: true;
      view_id: string;
      graph_id: string;
      project_id: string;
      limit: number;
      include_edges: boolean;
      nodes: StoryGraphNodeRecord[];
      edges: StoryGraphEdgeRecord[];
    }
  | ApiFailure;

export type StoryGraphEvidenceRecord = {
  evidence_id: string;
  graph_id: string;
  project_id: string;
  owner_type: string;
  owner_id: string;
  source_type: string;
  source_id: string;
  chapter_id: string;
  segment_id: string;
  confidence: number;
  created_at: string;
  updated_at: string;
};

export type StoryGraphEvidenceSummary =
  | {
      ok: true;
      graph_id: string;
      project_id: string;
      owner_type: string;
      owner_id: string;
      limit: number;
      items: StoryGraphEvidenceRecord[];
    }
  | ApiFailure;

export type StoryGraphLayoutSummary =
  | {
      ok: true;
      graph_id: string;
      project_id: string;
      view_id: string;
      layout: Record<string, unknown>;
      created_at: string;
      updated_at: string;
    }
  | ApiFailure;

export type StoryGraphClusterRecord = {
  cluster_id: string;
  graph_id: string;
  project_id: string;
  cluster_key: string;
  title: string;
  summary: string;
  node_count: number;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type StoryGraphClustersSummary =
  | {
      ok: true;
      graph_id: string;
      project_id: string;
      limit: number;
      items: StoryGraphClusterRecord[];
    }
  | ApiFailure;

export type StartWriterRunInput = ApiContext & {
  projectId: string;
  mode: "draft" | "continue" | "outline" | "review";
  instruction: string;
  options?: Record<string, unknown>;
};

export type CreateLLMChannelInput = ApiContext & {
  name: string;
  provider: string;
  baseUrl: string;
  apiKey: string;
  maxConcurrency: number;
  enabled: boolean;
};

export type UpdateLLMChannelInput = ApiContext & {
  channelId: string;
  name: string;
  baseUrl: string;
  apiKey?: string;
  maxConcurrency: number;
  enabled: boolean;
};

export type CreateAssetInput = ApiContext & {
  projectId: string;
  scope: string;
  assetType: string;
  category: string;
  lifecycle: string;
  title: string;
  summary: string;
  contentText: string;
  payload?: Record<string, unknown>;
  tags?: string[];
  sourceKind: string;
  sourceRef: string;
  enabled: boolean;
  pinned: boolean;
};

export type UpdateAssetInput = ApiContext & {
  assetId: string;
  scope?: string;
  assetType?: string;
  category?: string;
  lifecycle?: string;
  title?: string;
  summary?: string;
  contentText?: string;
  payload?: Record<string, unknown>;
  tags?: string[];
  sourceKind?: string;
  sourceRef?: string;
  enabled?: boolean;
  pinned?: boolean;
};

export type BulkActionAssetsInput = ApiContext & {
  projectId: string;
  action: string;
  assetIds: string[];
  targetLifecycle?: string;
  category?: string;
  enabled?: boolean;
  pinned?: boolean;
};

export type StartStyleExtractionInput = ApiContext & {
  projectId: string;
  materialText: string;
  sourceAssetId?: string;
  scope: string;
  options?: Record<string, unknown>;
};

export type StartAssetReindexInput = ApiContext & {
  projectId: string;
  scope: string;
  mode: string;
  options?: Record<string, unknown>;
};

export type StartStoryGraphBuildInput = ApiContext & {
  projectId: string;
  mode: string;
  options?: Record<string, unknown>;
};

export type StartStoryGraphBondGenerationInput = ApiContext & {
  projectId: string;
  graphId?: string;
  nodeIds: string[];
  focus: string;
  options?: Record<string, unknown>;
};

export type GetStoryGraphViewInput = ApiContext & {
  projectId: string;
  viewId: string;
  limit?: number;
  types?: string[];
  includeEdges?: boolean;
};

export type GetStoryGraphEvidenceInput = ApiContext & {
  projectId: string;
  ownerType: "node" | "edge";
  ownerId: string;
  limit?: number;
};

export type GetStoryGraphLayoutInput = ApiContext & {
  projectId: string;
  viewId: string;
};

export type GetStoryGraphClustersInput = ApiContext & {
  projectId: string;
  limit?: number;
};

export type CreateSourceFileUploadInput = ApiContext & {
  projectId: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  sha256: string;
  purpose: string;
};

export type CompleteSourceFileUploadInput = ApiContext & {
  uploadId: string;
};

export type UploadSourceFileObjectInput = ApiContext & {
  uploadId: string;
  file: Blob;
};

export type StartSeedRunInput = ApiContext & {
  projectId: string;
  uploadId: string;
  options?: Record<string, unknown>;
};

export type StartWorldlineSessionInput = ApiContext & {
  projectId: string;
  goal: string;
  anchorPathId?: string;
  options?: Record<string, unknown>;
};

export type StartWorldlineStepInput = ApiContext & {
  sessionId: string;
  mode: string;
  options?: Record<string, unknown>;
};

export type CreateWorldlinePreparationInput = ApiContext & {
  projectId: string;
  goal: string;
  anchorPathId?: string;
  options?: Record<string, unknown>;
};

export type InjectWorldlineVariableInput = ApiContext & {
  sessionId: string;
  name: string;
  description?: string;
  impactAxis?: string;
  locked?: boolean;
  source?: string;
};

export type CreateWorldlineSavedPathInput = ApiContext & {
  sessionId: string;
  title: string;
  summary?: string;
  selectedEventIds: string[];
  writerInstruction?: string;
};

export type AdoptWorldlineEventInput = ApiContext & {
  eventId: string;
  note?: string;
};

export type UpdateWorldlineEventInput = ApiContext & {
  eventId: string;
  title?: string;
  summary?: string;
  kind?: string;
};

export function apiBaseUrl() {
  return process.env.MIROFISH_API_BASE_URL ?? DEFAULT_API_BASE_URL;
}

export async function getCurrentUser(input: { actorUserId?: string; sessionCookie?: string }): Promise<CurrentUserSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/me`, {
      headers: currentUserHeaders(input),
      cache: "no-store",
    });

    return await decodeCurrentUserResponse(response);
  } catch (error) {
    return networkFailure(error, "CURRENT_USER_QUERY_FAILED");
  }
}

function currentUserHeaders(input: { actorUserId?: string; sessionCookie?: string }) {
  const headers: Record<string, string> = {};
  const sessionCookie = input.sessionCookie?.trim();
  const actorUserId = input.actorUserId?.trim();

  if (sessionCookie) {
    headers.Cookie = `mirofish_session=${sessionCookie}`;
  } else if (actorUserId) {
    headers["X-User-Id"] = actorUserId;
  }

  return headers;
}

export async function revokeCurrentSession(input: { sessionCookie?: string; csrfToken?: string }): Promise<SessionRevokeSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/auth/session`, {
      method: "DELETE",
      headers: sessionCookieHeaders(input),
      cache: "no-store",
    });
    if (response.ok) {
      return { ok: true };
    }

    const payload = await readLLMPayload(response);
    if (isApiFailure(payload)) {
      return payload;
    }
    return decodeError(payload, response.status, "SESSION_REVOKE_FAILED");
  } catch (error) {
    return networkFailure(error, "SESSION_REVOKE_FAILED");
  }
}

export async function getSessionCSRFToken(input: { sessionCookie?: string }): Promise<SessionCSRFTokenSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/auth/csrf-token`, {
      headers: sessionCookieHeaders(input),
      cache: "no-store",
    });
    const payload = await readLLMPayload(response);
    if (isApiFailure(payload)) {
      return payload;
    }
    if (!response.ok) {
      return decodeError(payload, response.status, "SESSION_CSRF_TOKEN_FAILED");
    }

    const csrfToken = requiredString(payload, "csrf_token");
    if (!csrfToken) {
      return invalidApiResponse("session csrf token response missing required fields");
    }
    return {
      ok: true,
      csrf_token: csrfToken,
    };
  } catch (error) {
    return networkFailure(error, "SESSION_CSRF_TOKEN_FAILED");
  }
}

function sessionCookieHeaders(input: { sessionCookie?: string; csrfToken?: string }) {
  const headers: Record<string, string> = {};
  const sessionCookie = input.sessionCookie?.trim();

  if (sessionCookie) {
    headers.Cookie = `mirofish_session=${sessionCookie}`;
  }
  const csrfToken = input.csrfToken?.trim();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  return headers;
}

export async function startWriterRun(input: StartWriterRunInput): Promise<WriterRunSummary> {
  const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/writer-runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...contextHeaders(input),
    },
    body: JSON.stringify({
      mode: input.mode,
      instruction: input.instruction,
      options: input.options ?? {},
    }),
    cache: "no-store",
  });

  return decodeWriterRunResponse(response);
}

export async function getWriterRunSummary(input: ApiContext & { runId: string }) {
  const response = await fetch(`${apiBaseUrl()}/v1/writer-runs/${input.runId}`, {
    headers: contextHeaders(input),
    cache: "no-store",
  });

  return decodeWriterRunResponse(response);
}

export async function getWriterRunEvents(
  input: ApiContext & { runId: string; afterEventId?: string },
): Promise<WriterRunEventsSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/writer-runs/${input.runId}/events`);
    if (input.afterEventId) {
      url.searchParams.set("after_event_id", input.afterEventId);
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWriterRunEventsResponse(response, input.runId, input.afterEventId ?? "");
  } catch (error) {
    return networkFailure(error, "WRITER_EVENTS_QUERY_FAILED");
  }
}

export async function getProjectManuscript(
  input: ApiContext & { projectId: string },
): Promise<ProjectManuscriptSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/manuscript`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeProjectManuscriptResponse(response);
  } catch (error) {
    return networkFailure(error, "MANUSCRIPT_QUERY_FAILED");
  }
}

export async function getProjectManuscriptExportManifest(
  input: ApiContext & { projectId: string },
): Promise<ProjectManuscriptExportManifestSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/manuscript/export`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeProjectManuscriptExportManifestResponse(response);
  } catch (error) {
    return networkFailure(error, "MANUSCRIPT_EXPORT_QUERY_FAILED");
  }
}

export async function getWorkflowRunSummary(
  input: ApiContext & { runId: string },
): Promise<WorkflowRunSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/workflow-runs/${input.runId}`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorkflowRunResponse(response);
  } catch (error) {
    return networkFailure(error, "WORKFLOW_QUERY_FAILED");
  }
}

export async function getWorkflowRunEvents(
  input: ApiContext & { runId: string; afterEventId?: string },
): Promise<WorkflowRunEventsSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/workflow-runs/${input.runId}/events`);
    if (input.afterEventId) {
      url.searchParams.set("after_event_id", input.afterEventId);
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorkflowRunEventsResponse(response, input.runId, input.afterEventId ?? "");
  } catch (error) {
    return networkFailure(error, "WORKFLOW_EVENTS_QUERY_FAILED");
  }
}

export async function getProjectSourceFiles(
  input: ApiContext & { projectId: string },
): Promise<SourceFilesSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/source-files`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeSourceFilesResponse(response);
  } catch (error) {
    return networkFailure(error, "SOURCE_FILE_QUERY_FAILED");
  }
}

export async function getProjectOverview(
  input: ApiContext & { projectId: string },
): Promise<ProjectOverviewSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/overview`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeProjectOverviewResponse(response);
  } catch (error) {
    return networkFailure(error, "PROJECT_OVERVIEW_QUERY_FAILED");
  }
}

export async function getProjectReadinessSnapshot(
  input: ApiContext & { projectId: string },
): Promise<ProjectReadinessSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/readiness`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeProjectReadinessResponse(response);
  } catch (error) {
    return networkFailure(error, "PROJECT_READINESS_QUERY_FAILED");
  }
}

export async function createSourceFileUpload(
  input: CreateSourceFileUploadInput,
): Promise<SourceFileSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/uploads`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        filename: input.filename,
        mime_type: input.mimeType,
        size_bytes: input.sizeBytes,
        sha256: input.sha256,
        purpose: input.purpose,
      }),
      cache: "no-store",
    });

    return await decodeSourceFileResponse(response, "SOURCE_FILE_ADMISSION_FAILED");
  } catch (error) {
    return networkFailure(error, "SOURCE_FILE_ADMISSION_FAILED");
  }
}

export async function completeSourceFileUpload(
  input: CompleteSourceFileUploadInput,
): Promise<SourceFileSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/uploads/${input.uploadId}/complete`, {
      method: "POST",
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeSourceFileResponse(response, "SOURCE_FILE_COMPLETE_FAILED");
  } catch (error) {
    return networkFailure(error, "SOURCE_FILE_COMPLETE_FAILED");
  }
}

export async function uploadSourceFileObject(
  input: UploadSourceFileObjectInput,
): Promise<SourceFileObjectUploadSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/uploads/${input.uploadId}/object`, {
      method: "PUT",
      headers: {
        ...contextHeaders(input),
        "Content-Type": input.file.type || "application/octet-stream",
      },
      body: input.file,
      cache: "no-store",
    });

    return await decodeSourceFileObjectUploadResponse(response, input.uploadId);
  } catch (error) {
    return networkFailure(error, "SOURCE_FILE_OBJECT_UPLOAD_FAILED");
  }
}

export async function startSeedRun(input: StartSeedRunInput): Promise<SeedRunStartSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/seed-runs`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        upload_id: input.uploadId,
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeSeedRunStartResponse(response);
  } catch (error) {
    return networkFailure(error, "SEED_RUN_START_FAILED");
  }
}

export async function cancelSeedRun(input: ApiContext & { runId: string }): Promise<WorkflowControlSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/seed-runs/${input.runId}/cancel`, {
      method: "POST",
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorkflowControlResponse(response, "WORKFLOW_CANCEL_FAILED");
  } catch (error) {
    return networkFailure(error, "WORKFLOW_CANCEL_FAILED");
  }
}

export async function retrySeedRun(input: ApiContext & { runId: string }): Promise<WorkflowControlSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/seed-runs/${input.runId}/retry`, {
      method: "POST",
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorkflowControlResponse(response, "WORKFLOW_RETRY_FAILED");
  } catch (error) {
    return networkFailure(error, "WORKFLOW_RETRY_FAILED");
  }
}

export async function getProjectSeedRuns(
  input: ApiContext & { projectId: string },
): Promise<SeedRunsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/seed-runs`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeSeedRunsResponse(response);
  } catch (error) {
    return networkFailure(error, "SEED_RUN_QUERY_FAILED");
  }
}

export async function getSeedRunSummary(input: ApiContext & { runId: string }): Promise<WorkflowRunSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/seed-runs/${input.runId}`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorkflowRunResponse(response);
  } catch (error) {
    return networkFailure(error, "SEED_RUN_QUERY_FAILED");
  }
}

export async function getSeedRunEvents(
  input: ApiContext & { runId: string; afterEventId?: string },
): Promise<WorkflowRunEventsSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/seed-runs/${input.runId}/events`);
    if (input.afterEventId) {
      url.searchParams.set("after_event_id", input.afterEventId);
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorkflowRunEventsResponse(response, input.runId, input.afterEventId ?? "");
  } catch (error) {
    return networkFailure(error, "SEED_RUN_EVENTS_QUERY_FAILED");
  }
}

export async function getAgentTraceEvents(
  input: ApiContext & { projectId: string; traceId: string; includeFull?: boolean },
): Promise<AgentTraceEventsSummary> {
  const url = new URL(
    `${apiBaseUrl()}/v1/projects/${input.projectId}/agent-traces/${input.traceId}/events`,
  );
  if (input.includeFull) {
    url.searchParams.set("include_full", "true");
  }

  const response = await fetch(url, {
    headers: contextHeaders(input),
    cache: "no-store",
  });

  return decodeTraceEventsResponse(response, input.projectId, input.traceId, Boolean(input.includeFull));
}

export async function exportAgentTrace(
  input: ApiContext & { projectId: string; traceId: string; includeFull?: boolean },
): Promise<AgentTraceEventsSummary> {
  const response = await fetch(
    `${apiBaseUrl()}/v1/projects/${input.projectId}/agent-traces/${input.traceId}/export`,
    {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ include_full: Boolean(input.includeFull) }),
      cache: "no-store",
    },
  );

  return decodeTraceExportResponse(response, input.projectId, input.traceId);
}

export async function resolveLLMModuleBinding(
  input: ApiContext & { projectId: string; moduleKey: string },
): Promise<LLMModuleResolutionSummary> {
  try {
    const response = await fetch(
      `${apiBaseUrl()}/v1/projects/${input.projectId}/llm/module-bindings/${input.moduleKey}/resolution`,
      {
        headers: contextHeaders(input),
        cache: "no-store",
      },
    );

    return await decodeLLMResolutionResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_MODULE_RESOLUTION_FAILED");
  }
}

export async function getLLMModuleBindings(
  input: ApiContext & { projectId: string },
): Promise<LLMModuleBindingsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/module-bindings`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMModuleBindingsResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_BINDING_QUERY_FAILED");
  }
}

export async function getLLMModules(input: ApiContext & { projectId: string }): Promise<LLMModulesSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/modules`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMModulesResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_MODULE_REGISTRY_QUERY_FAILED");
  }
}

export async function getLLMSettings(input: ApiContext): Promise<LLMSettingsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/llm/settings`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMSettingsResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_SETTINGS_QUERY_FAILED");
  }
}

export async function getLLMChannels(
  input: ApiContext & { projectId: string },
): Promise<LLMChannelsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/channels`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMChannelsResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_CATALOG_QUERY_FAILED");
  }
}

export async function getLLMChannelModels(
  input: ApiContext & { projectId: string; channelId: string },
): Promise<LLMChannelModelsSummary> {
  try {
    const response = await fetch(
      `${apiBaseUrl()}/v1/projects/${input.projectId}/llm/channels/${input.channelId}/models`,
      {
        headers: contextHeaders(input),
        cache: "no-store",
      },
    );

    return await decodeLLMChannelModelsResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_CATALOG_QUERY_FAILED");
  }
}

export async function createLLMChannel(input: CreateLLMChannelInput): Promise<LLMChannelSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/llm/channels`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: input.name,
        provider: input.provider,
        base_url: input.baseUrl,
        api_key: input.apiKey,
        max_concurrency: input.maxConcurrency,
        enabled: input.enabled,
      }),
      cache: "no-store",
    });

    return await decodeLLMChannelResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_CHANNEL_UPDATE_FAILED");
  }
}

export async function updateLLMChannel(input: UpdateLLMChannelInput): Promise<LLMChannelSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/llm/channels/${input.channelId}`, {
      method: "PATCH",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: input.name,
        base_url: input.baseUrl,
        api_key: input.apiKey ?? "",
        max_concurrency: input.maxConcurrency,
        enabled: input.enabled,
      }),
      cache: "no-store",
    });

    return await decodeLLMChannelResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_CHANNEL_UPDATE_FAILED");
  }
}

export async function deleteLLMChannel(
  input: ApiContext & { channelId: string },
): Promise<LLMChannelSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/llm/channels/${input.channelId}`, {
      method: "DELETE",
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMChannelResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_CHANNEL_UPDATE_FAILED");
  }
}

export async function syncLLMChannelModels(
  input: ApiContext & { channelId: string },
): Promise<LLMModelSyncSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/llm/channels/${input.channelId}/sync-models`, {
      method: "POST",
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMModelSyncResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_MODEL_SYNC_FAILED");
  }
}

export async function upsertLLMModuleBinding(
  input: ApiContext & {
    projectId: string;
    moduleKey: string;
    channelId: string;
    modelId: string;
    settings?: Record<string, unknown>;
  },
): Promise<LLMModuleBindingSummary> {
  try {
    const response = await fetch(
      `${apiBaseUrl()}/v1/projects/${input.projectId}/llm/module-bindings/${input.moduleKey}`,
      {
        method: "PUT",
        headers: {
          ...contextHeaders(input),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          channel_id: input.channelId,
          model_id: input.modelId,
          settings: input.settings ?? {},
        }),
        cache: "no-store",
      },
    );

    return await decodeLLMModuleBindingResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_BINDING_UPDATE_FAILED");
  }
}

export async function deleteLLMModuleBinding(
  input: ApiContext & { projectId: string; moduleKey: string },
): Promise<LLMModuleBindingSummary> {
  try {
    const response = await fetch(
      `${apiBaseUrl()}/v1/projects/${input.projectId}/llm/module-bindings/${input.moduleKey}`,
      {
        method: "DELETE",
        headers: contextHeaders(input),
        cache: "no-store",
      },
    );

    return await decodeLLMModuleBindingResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_BINDING_DELETE_FAILED");
  }
}

export async function getLLMActivity(
  input: ApiContext & { projectId: string; moduleKey?: string; runId?: string },
): Promise<LLMActivitySummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/activity`);
    addTelemetryFilters(url, input);

    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMActivityResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_ACTIVITY_QUERY_FAILED");
  }
}

export async function getLLMUsage(
  input: ApiContext & { projectId: string; moduleKey?: string; runId?: string },
): Promise<LLMUsageSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/usage`);
    addTelemetryFilters(url, input);

    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeLLMUsageResponse(response);
  } catch (error) {
    return networkFailure(error, "LLM_ACTIVITY_QUERY_FAILED");
  }
}

export async function getProjectAssets(
  input: ApiContext & { projectId: string },
): Promise<AssetListSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/assets`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeAssetListResponse(response);
  } catch (error) {
    return networkFailure(error, "ASSET_QUERY_FAILED");
  }
}

export async function getWorldlineSavedPaths(
  input: ApiContext & { projectId: string },
): Promise<WorldlineSavedPathsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/worldline/saved-paths`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorldlineSavedPathsResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_QUERY_FAILED");
  }
}

export async function getWorldlineSessions(
  input: ApiContext & { projectId: string },
): Promise<WorldlineSessionsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/worldline-sessions`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorldlineSessionsResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_SESSION_QUERY_FAILED");
  }
}

export async function getWorldlineSession(
  input: ApiContext & { sessionId: string },
): Promise<WorldlineSessionSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-sessions/${input.sessionId}`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorldlineSessionResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_SESSION_QUERY_FAILED");
  }
}

export async function getWorldlineTimeline(
  input: ApiContext & { sessionId: string },
): Promise<WorldlineTimelineSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-sessions/${input.sessionId}/timeline`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorldlineTimelineResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_TIMELINE_QUERY_FAILED");
  }
}

export async function getWorldlineEvents(
  input: ApiContext & { sessionId: string; status?: string },
): Promise<WorldlineEventsSummary> {
  try {
    const query = input.status ? `?status=${encodeURIComponent(input.status)}` : "";
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-sessions/${input.sessionId}/events${query}`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorldlineEventsResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_EVENT_QUERY_FAILED");
  }
}

export async function createWorldlineSavedPath(
  input: CreateWorldlineSavedPathInput,
): Promise<WorldlineSavedPathSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-sessions/${input.sessionId}/saved-paths`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        title: input.title,
        summary: input.summary ?? "",
        selected_event_ids: input.selectedEventIds,
        writer_instruction: input.writerInstruction ?? "",
      }),
      cache: "no-store",
    });

    return await decodeWorldlineSavedPathResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_SAVED_PATH_CREATE_FAILED");
  }
}

export async function adoptWorldlineEvent(
  input: AdoptWorldlineEventInput,
): Promise<WorldlineEventSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-events/${input.eventId}/adoptions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        note: input.note ?? "",
      }),
      cache: "no-store",
    });

    return await decodeWorldlineEventResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_EVENT_ADOPTION_FAILED");
  }
}

export async function updateWorldlineEvent(
  input: UpdateWorldlineEventInput,
): Promise<WorldlineEventSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-events/${input.eventId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        title: input.title ?? "",
        summary: input.summary ?? "",
        kind: input.kind ?? "",
      }),
      cache: "no-store",
    });

    return await decodeWorldlineEventResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_EVENT_MUTATION_FAILED");
  }
}

export async function startWorldlineSession(
  input: StartWorldlineSessionInput,
): Promise<WorldlineSessionStartSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/worldline-sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        goal: input.goal,
        anchor_path_id: input.anchorPathId ?? "",
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeWorldlineSessionStartResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_SESSION_START_FAILED");
  }
}

export async function startWorldlineStep(
  input: StartWorldlineStepInput,
): Promise<WorldlineStepStartSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-sessions/${input.sessionId}/steps`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        mode: input.mode,
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeWorldlineStepStartResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_STEP_START_FAILED");
  }
}

export async function injectWorldlineVariable(
  input: InjectWorldlineVariableInput,
): Promise<WorldlineVariableSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-sessions/${input.sessionId}/variables`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        name: input.name,
        description: input.description ?? "",
        impact_axis: input.impactAxis ?? "",
        locked: Boolean(input.locked),
        source: input.source ?? "author",
      }),
      cache: "no-store",
    });

    return await decodeWorldlineVariableResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_VARIABLE_INJECTION_FAILED");
  }
}

export async function listCharacterInteractions(
  input: ApiContext & { projectId: string; status?: string },
): Promise<CharacterInteractionsSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/character-interactions`);
    if (input.status) {
      url.searchParams.set("status", input.status);
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeCharacterInteractionsResponse(response);
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_QUERY_FAILED");
  }
}

export async function createCharacterInteraction(
  input: CreateCharacterInteractionInput,
): Promise<CharacterInteractionSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/character-interactions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        worldline_session_id: input.worldlineSessionId ?? "",
        anchor_type: input.anchorType ?? "",
        anchor_id: input.anchorId ?? "",
        pov_agent_id: input.povAgentId ?? "",
        mode: input.mode,
        title: input.title,
        summary: input.summary ?? "",
        metadata: input.metadata ?? {},
      }),
      cache: "no-store",
    });

    return await decodeCharacterInteractionResponse(response, "CHARACTER_INTERACTION_CREATE_FAILED");
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_CREATE_FAILED");
  }
}

export async function updateCharacterInteractionStatus(
  input: UpdateCharacterInteractionStatusInput,
): Promise<CharacterInteractionSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/character-interactions/${input.interactionId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        status: input.status,
      }),
      cache: "no-store",
    });

    return await decodeCharacterInteractionResponse(response, "CHARACTER_INTERACTION_STATUS_UPDATE_FAILED");
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_STATUS_UPDATE_FAILED");
  }
}

export async function getCharacterInteraction(
  input: ApiContext & { interactionId: string },
): Promise<CharacterInteractionDetailSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/character-interactions/${input.interactionId}`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeCharacterInteractionDetailResponse(response);
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_QUERY_FAILED");
  }
}

export async function listCharacterInteractionTurns(
  input: ApiContext & { interactionId: string },
): Promise<CharacterInteractionTurnsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/character-interactions/${input.interactionId}/turns`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeCharacterInteractionTurnsResponse(response);
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_TURN_QUERY_FAILED");
  }
}

export async function appendCharacterInteractionTurn(
  input: ApiContext & {
    interactionId: string;
    actorType: string;
    actorId?: string;
    turnKind: string;
    summary: string;
    action?: Record<string, unknown>;
    worldStateDelta?: Record<string, unknown>;
    traceId?: string;
  },
): Promise<CharacterInteractionTurnSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/character-interactions/${input.interactionId}/turns`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        actor_type: input.actorType,
        actor_id: input.actorId ?? "",
        turn_kind: input.turnKind,
        summary: input.summary,
        action: input.action ?? {},
        world_state_delta: input.worldStateDelta ?? {},
        trace_id: input.traceId ?? "",
      }),
      cache: "no-store",
    });

    return await decodeCharacterInteractionTurnResponse(response);
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_TURN_CREATE_FAILED");
  }
}

export async function getCharacterInteractionEvents(
  input: ApiContext & { interactionId: string; afterEventId?: string },
): Promise<CharacterInteractionEventsSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/character-interactions/${input.interactionId}/events`);
    if (input.afterEventId) {
      url.searchParams.set("after_event_id", input.afterEventId);
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeCharacterInteractionEventsResponse(response);
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_EVENTS_FAILED");
  }
}

export async function convertCharacterInteractionToChapterDraft(
  input: ApiContext & {
    interactionId: string;
    targetChapterId?: string;
    povMode?: string;
    styleAssetIds?: string[];
    authorInstruction?: string;
  },
): Promise<CharacterInteractionChapterDraftSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/character-interactions/${input.interactionId}/chapter-drafts`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        target_chapter_id: input.targetChapterId ?? "",
        pov_mode: input.povMode ?? "",
        style_asset_ids: input.styleAssetIds ?? [],
        author_instruction: input.authorInstruction ?? "",
      }),
      cache: "no-store",
    });

    return await decodeCharacterInteractionChapterDraftResponse(response);
  } catch (error) {
    return networkFailure(error, "CHARACTER_INTERACTION_CHAPTER_DRAFT_FAILED");
  }
}

export async function createWorldlinePreparation(
  input: CreateWorldlinePreparationInput,
): Promise<WorldlinePreparationSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/worldlines/preparations`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...contextHeaders(input),
      },
      body: JSON.stringify({
        goal: input.goal,
        anchor_path_id: input.anchorPathId ?? "",
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeWorldlinePreparationResponse(response, "WORLDLINE_PREPARATION_CREATE_FAILED");
  } catch (error) {
    return networkFailure(error, "WORLDLINE_PREPARATION_CREATE_FAILED");
  }
}

export async function getWorldlinePreparation(
  input: ApiContext & { prepareId: string },
): Promise<WorldlinePreparationSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-preparations/${input.prepareId}`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorldlinePreparationResponse(response, "WORLDLINE_PREPARATION_QUERY_FAILED");
  } catch (error) {
    return networkFailure(error, "WORLDLINE_PREPARATION_QUERY_FAILED");
  }
}

export async function getWorldlinePreparedAgents(
  input: ApiContext & { prepareId: string },
): Promise<WorldlinePreparedAgentsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/worldline-preparations/${input.prepareId}/agents`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeWorldlinePreparedAgentsResponse(response);
  } catch (error) {
    return networkFailure(error, "WORLDLINE_PREPARED_AGENTS_QUERY_FAILED");
  }
}

export async function getAssetFacets(
  input: ApiContext & { projectId: string },
): Promise<AssetFacetsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/assets/facets`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeAssetFacetsResponse(response);
  } catch (error) {
    return networkFailure(error, "ASSET_QUERY_FAILED");
  }
}

export async function searchAssets(
  input: ApiContext & { projectId: string; query: string },
): Promise<AssetSearchSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/assets/search`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        project_id: input.projectId,
        query: input.query,
      }),
      cache: "no-store",
    });

    return await decodeAssetSearchResponse(response);
  } catch (error) {
    return networkFailure(error, "ASSET_SEARCH_FAILED");
  }
}

export async function getArchiveAssetMemories(
  input: ApiContext & { projectId: string; assetId: string },
): Promise<ArchiveMemorySummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/archive-assets/${input.assetId}/memories`);
    url.searchParams.set("project_id", input.projectId);
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeArchiveMemoryResponse(response);
  } catch (error) {
    return networkFailure(error, "ARCHIVE_MEMORY_QUERY_FAILED");
  }
}

export async function getArchiveAssetMemoryEvents(
  input: ApiContext & { projectId: string; assetId: string },
): Promise<ArchiveMemoryEventsSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/archive-assets/${input.assetId}/memory-events`);
    url.searchParams.set("project_id", input.projectId);
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeArchiveMemoryEventsResponse(response);
  } catch (error) {
    return networkFailure(error, "ARCHIVE_MEMORY_QUERY_FAILED");
  }
}

export async function adoptArchiveMemory(
  input: ApiContext & { projectId: string; memoryId: string },
): Promise<ArchiveMemoryReviewSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/archive-memories/${input.memoryId}/adoptions`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        project_id: input.projectId,
      }),
      cache: "no-store",
    });

    return await decodeArchiveMemoryReviewResponse(response, "ARCHIVE_MEMORY_REVIEW_FAILED");
  } catch (error) {
    return networkFailure(error, "ARCHIVE_MEMORY_REVIEW_FAILED");
  }
}

export async function rejectArchiveMemory(
  input: ApiContext & { projectId: string; memoryId: string },
): Promise<ArchiveMemoryReviewSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/archive-memories/${input.memoryId}/rejections`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        project_id: input.projectId,
      }),
      cache: "no-store",
    });

    return await decodeArchiveMemoryReviewResponse(response, "ARCHIVE_MEMORY_REVIEW_FAILED");
  } catch (error) {
    return networkFailure(error, "ARCHIVE_MEMORY_REVIEW_FAILED");
  }
}

export async function createAsset(input: CreateAssetInput): Promise<AssetSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/assets`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        scope: input.scope,
        asset_type: input.assetType,
        category: input.category,
        lifecycle: input.lifecycle,
        title: input.title,
        summary: input.summary,
        content_text: input.contentText,
        payload: input.payload ?? {},
        tags: input.tags ?? [],
        source_kind: input.sourceKind,
        source_ref: input.sourceRef,
        enabled: input.enabled,
        pinned: input.pinned,
      }),
      cache: "no-store",
    });

    return await decodeAssetResponse(response, "ASSET_MUTATION_FAILED");
  } catch (error) {
    return networkFailure(error, "ASSET_MUTATION_FAILED");
  }
}

export async function updateAsset(input: UpdateAssetInput): Promise<AssetSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/assets/${input.assetId}`, {
      method: "PATCH",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        scope: input.scope,
        asset_type: input.assetType,
        category: input.category,
        lifecycle: input.lifecycle,
        title: input.title,
        summary: input.summary,
        content_text: input.contentText,
        payload: input.payload,
        tags: input.tags,
        source_kind: input.sourceKind,
        source_ref: input.sourceRef,
        enabled: input.enabled,
        pinned: input.pinned,
      }),
      cache: "no-store",
    });

    return await decodeAssetResponse(response, "ASSET_MUTATION_FAILED");
  } catch (error) {
    return networkFailure(error, "ASSET_MUTATION_FAILED");
  }
}

export async function deleteAsset(
  input: ApiContext & { assetId: string },
): Promise<AssetDeleteSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/assets/${input.assetId}`, {
      method: "DELETE",
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeAssetDeleteResponse(response);
  } catch (error) {
    return networkFailure(error, "ASSET_MUTATION_FAILED");
  }
}

export async function adoptAsset(
  input: ApiContext & { assetId: string; targetLifecycle: "canon" | "material" },
): Promise<AssetSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/assets/${input.assetId}/adoptions`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        target_lifecycle: input.targetLifecycle,
      }),
      cache: "no-store",
    });

    return await decodeAssetResponse(response, "ASSET_ADOPTION_FAILED");
  } catch (error) {
    return networkFailure(error, "ASSET_ADOPTION_FAILED");
  }
}

export async function bulkActionAssets(input: BulkActionAssetsInput): Promise<AssetBulkActionSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/assets/bulk-actions`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        project_id: input.projectId,
        action: input.action,
        asset_ids: input.assetIds,
        target_lifecycle: input.targetLifecycle ?? "",
        category: input.category ?? "",
        enabled: input.enabled,
        pinned: input.pinned,
      }),
      cache: "no-store",
    });

    return await decodeAssetBulkActionResponse(response);
  } catch (error) {
    return networkFailure(error, "ASSET_BULK_ACTION_FAILED");
  }
}

export async function startAssetIngestion(
  input: ApiContext & {
    projectId: string;
    materialText: string;
    hintType: string;
    scope: string;
    options?: Record<string, unknown>;
  },
): Promise<AssetIngestionSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/asset-ingestions`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        material_text: input.materialText,
        hint_type: input.hintType,
        scope: input.scope,
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeAssetIngestionResponse(response);
  } catch (error) {
    return networkFailure(error, "ASSET_INGESTION_START_FAILED");
  }
}

export async function startAssetReindex(input: StartAssetReindexInput): Promise<AssetReindexSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/assets/reindex`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        scope: input.scope,
        mode: input.mode,
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeAssetReindexResponse(response);
  } catch (error) {
    return networkFailure(error, "ASSET_REINDEX_START_FAILED");
  }
}

export async function startStyleExtraction(
  input: StartStyleExtractionInput,
): Promise<StyleExtractionSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/style-extractions`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        material_text: input.materialText,
        source_asset_id: input.sourceAssetId ?? "",
        scope: input.scope,
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeStyleExtractionResponse(response);
  } catch (error) {
    return networkFailure(error, "STYLE_EXTRACTION_START_FAILED");
  }
}

export async function getStoryGraphCurrent(
  input: ApiContext & { projectId: string },
): Promise<StoryGraphCurrentSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/story-graph/current`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeStoryGraphCurrentResponse(response);
  } catch (error) {
    return networkFailure(error, "STORY_GRAPH_QUERY_FAILED");
  }
}

export async function getStoryGraphView(input: GetStoryGraphViewInput): Promise<StoryGraphViewSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/story-graph/views/${input.viewId}`);
    if (input.limit) {
      url.searchParams.set("limit", String(input.limit));
    }
    if (input.types && input.types.length > 0) {
      url.searchParams.set("types", input.types.join(","));
    }
    if (input.includeEdges) {
      url.searchParams.set("include_edges", "true");
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeStoryGraphViewResponse(response);
  } catch (error) {
    return networkFailure(error, "STORY_GRAPH_QUERY_FAILED");
  }
}

export async function getStoryGraphEvidence(input: GetStoryGraphEvidenceInput): Promise<StoryGraphEvidenceSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/story-graph/${input.ownerType}s/${input.ownerId}/evidence`);
    if (input.limit) {
      url.searchParams.set("limit", String(input.limit));
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeStoryGraphEvidenceResponse(response);
  } catch (error) {
    return networkFailure(error, "STORY_GRAPH_QUERY_FAILED");
  }
}

export async function getStoryGraphLayout(input: GetStoryGraphLayoutInput): Promise<StoryGraphLayoutSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/story-graph/layouts/${input.viewId}`, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeStoryGraphLayoutResponse(response);
  } catch (error) {
    return networkFailure(error, "STORY_GRAPH_QUERY_FAILED");
  }
}

export async function getStoryGraphClusters(input: GetStoryGraphClustersInput): Promise<StoryGraphClustersSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/story-graph/clusters`);
    if (input.limit) {
      url.searchParams.set("limit", String(input.limit));
    }
    const response = await fetch(url, {
      headers: contextHeaders(input),
      cache: "no-store",
    });

    return await decodeStoryGraphClustersResponse(response);
  } catch (error) {
    return networkFailure(error, "STORY_GRAPH_QUERY_FAILED");
  }
}

export async function startStoryGraphBuild(
  input: StartStoryGraphBuildInput,
): Promise<StoryGraphBuildSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/story-graph/builds`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mode: input.mode,
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeStoryGraphBuildResponse(response);
  } catch (error) {
    return networkFailure(error, "STORY_GRAPH_BUILD_START_FAILED");
  }
}

export async function startStoryGraphBondGeneration(
  input: StartStoryGraphBondGenerationInput,
): Promise<StoryGraphBondGenerationSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/story-graph/bond-generations`, {
      method: "POST",
      headers: {
        ...contextHeaders(input),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        graph_id: input.graphId ?? "",
        node_ids: input.nodeIds,
        focus: input.focus,
        options: input.options ?? {},
      }),
      cache: "no-store",
    });

    return await decodeStoryGraphBondGenerationResponse(response);
  } catch (error) {
    return networkFailure(error, "STORY_GRAPH_BOND_START_FAILED");
  }
}

async function decodeCurrentUserResponse(response: Response): Promise<CurrentUserSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "CURRENT_USER_QUERY_FAILED");
  }

  const user = recordFromUnknown(payload.user);
  const activeTenants = requiredArray(payload, "active_tenants");
  const activeProjects = requiredArray(payload, "active_projects");
  if (activeTenants === null || activeProjects === null) {
    return invalidApiResponse("current user response missing required fields");
  }

  const userId = requiredString(user, "user_id");
  const tenantSummaries = decodeTenantMembershipSummaries(activeTenants);
  const projectSummaries = decodeProjectMembershipSummaries(activeProjects);
  if (!userId || tenantSummaries === null || projectSummaries === null) {
    return invalidApiResponse("current user response missing required fields");
  }

  return {
    ok: true,
    user_id: userId,
    email: requiredString(user, "email"),
    display_name: requiredString(user, "display_name"),
    avatar_url: requiredString(user, "avatar_url"),
    active_tenants: tenantSummaries,
    active_projects: projectSummaries,
  };
}

async function decodeWriterRunResponse(response: Response): Promise<WriterRunSummary> {
  const payload = (await response.json()) as Record<string, unknown>;
  if (!response.ok) {
    return decodeError(payload, response.status, "WORKFLOW_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const traceId = requiredString(payload, "trace_id");
  const projectId = requiredString(payload, "project_id");
  const status = requiredString(payload, "status");
  if (!runId || !traceId || !projectId || !status) {
    return invalidApiResponse("writer run response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    trace_id: traceId,
    project_id: projectId,
    status,
  };
}

async function decodeWriterRunEventsResponse(
  response: Response,
  runId: string,
  afterEventId: string,
): Promise<WriterRunEventsSummary> {
  const payload = (await response.json()) as Record<string, unknown>;
  if (!response.ok) {
    return decodeError(payload, response.status, "WRITER_EVENTS_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("writer event response missing items");
  }

  return {
    ok: true,
    run_id: runId,
    after_event_id: afterEventId,
    items: payload.items.map((item) => decodeWriterRunEvent(item)),
  };
}

async function decodeProjectManuscriptResponse(response: Response): Promise<ProjectManuscriptSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "MANUSCRIPT_QUERY_FAILED");
  }

  const projectId = requiredString(payload, "project_id");
  if (!projectId || !Array.isArray(payload.blocks)) {
    return invalidApiResponse("manuscript response missing required metadata fields");
  }

  return {
    ok: true,
    project_id: projectId,
    blocks: payload.blocks.map((item) => decodeManuscriptBlockMetadata(item)),
  };
}

async function decodeProjectManuscriptExportManifestResponse(
  response: Response,
): Promise<ProjectManuscriptExportManifestSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "MANUSCRIPT_EXPORT_QUERY_FAILED");
  }

  const projectId = requiredString(payload, "project_id");
  if (!projectId) {
    return invalidApiResponse("manuscript export manifest response missing project_id");
  }

  return {
    ok: true,
    project_id: projectId,
    format: requiredString(payload, "format"),
    status: requiredString(payload, "status"),
    block_count: numberFromUnknown(payload.block_count),
    total_word_count: numberFromUnknown(payload.total_word_count),
    generated_at: requiredString(payload, "generated_at"),
    blocks: arrayFromUnknown(payload.blocks).map((item) => decodeManuscriptExportManifestBlock(item)),
  };
}

async function decodeWorkflowRunResponse(response: Response): Promise<WorkflowRunSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORKFLOW_QUERY_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const workflowType = requiredString(payload, "workflow_type");
  const projectId = requiredString(payload, "project_id");
  const status = requiredString(payload, "status");
  if (!runId || !workflowType || !projectId || !status) {
    return invalidApiResponse("workflow run response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    workflow_type: workflowType,
    project_id: projectId,
    status,
    progress: numberFromUnknown(payload.progress),
    message: requiredString(payload, "message"),
    error_code: requiredString(payload, "error_code"),
    error_message: requiredString(payload, "error_message"),
    created_at: requiredString(payload, "created_at"),
    updated_at: requiredString(payload, "updated_at"),
  };
}

async function decodeWorkflowRunEventsResponse(
  response: Response,
  runId: string,
  afterEventId: string,
): Promise<WorkflowRunEventsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORKFLOW_EVENTS_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("workflow event response missing items");
  }

  return {
    ok: true,
    run_id: runId,
    after_event_id: afterEventId,
    items: payload.items.map((item) => decodeWorkflowRunEvent(item)),
  };
}

async function decodeSourceFilesResponse(response: Response): Promise<SourceFilesSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "SOURCE_FILE_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("source file response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeSourceFileRecord(item)),
  };
}

async function decodeSourceFileResponse(
  response: Response,
  fallbackCode: string,
): Promise<SourceFileSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, fallbackCode);
  }

  return {
    ok: true,
    ...decodeSourceFileRecord(payload),
  };
}

async function decodeProjectReadinessResponse(response: Response): Promise<ProjectReadinessSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "PROJECT_READINESS_QUERY_FAILED");
  }

  return {
    ok: true,
    ...decodeProjectReadinessSnapshot(payload),
  };
}

async function decodeProjectOverviewResponse(response: Response): Promise<ProjectOverviewSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "PROJECT_OVERVIEW_QUERY_FAILED");
  }

  return {
    ok: true,
    ...decodeProjectOverviewRecord(payload),
  };
}

async function decodeSourceFileObjectUploadResponse(
  response: Response,
  uploadId: string,
): Promise<SourceFileObjectUploadSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "SOURCE_FILE_OBJECT_UPLOAD_FAILED");
  }

  const responseUploadId = requiredString(payload, "upload_id");
  const status = requiredString(payload, "status");
  if (!responseUploadId || !status) {
    return invalidApiResponse("source file object upload response missing required fields");
  }

  return {
    ok: true,
    upload_id: responseUploadId || uploadId,
    status,
  };
}

async function decodeSeedRunStartResponse(response: Response): Promise<SeedRunStartSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "SEED_RUN_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !workflowType || !status) {
    return invalidApiResponse("seed run start response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeWorkflowControlResponse(
  response: Response,
  fallbackCode: string,
): Promise<WorkflowControlSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, fallbackCode);
  }

  const runId = requiredString(payload, "run_id");
  const status = requiredString(payload, "status");
  if (!runId || !status) {
    return invalidApiResponse("workflow control response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    status,
  };
}

async function decodeSeedRunsResponse(response: Response): Promise<SeedRunsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "SEED_RUN_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("seed run response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeWorkflowRunRecord(item)),
  };
}

async function decodeTraceEventsResponse(
  response: Response,
  projectId: string,
  traceId: string,
  includeFull: boolean,
): Promise<AgentTraceEventsSummary> {
  const payload = (await response.json()) as Record<string, unknown>;
  if (!response.ok) {
    return decodeError(payload, response.status, "AGENT_TRACE_QUERY_FAILED");
  }

  return decodeTraceItems(payload, projectId, traceId, includeFull);
}

async function decodeTraceExportResponse(
  response: Response,
  projectId: string,
  traceId: string,
): Promise<AgentTraceEventsSummary> {
  const payload = (await response.json()) as Record<string, unknown>;
  if (!response.ok) {
    return decodeError(payload, response.status, "AGENT_TRACE_QUERY_FAILED");
  }

  const exportedTraceId = requiredString(payload, "trace_id") || traceId;
  const exportedProjectId = requiredString(payload, "project_id") || projectId;
  return decodeTraceItems(payload, exportedProjectId, exportedTraceId, Boolean(payload.include_full));
}

async function decodeLLMResolutionResponse(response: Response): Promise<LLMModuleResolutionSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_MODULE_UNBOUND");
  }

  const moduleKey = requiredString(payload, "module_key");
  const channelId = requiredString(payload, "channel_id");
  const modelId = requiredString(payload, "model_id");
  const provider = requiredString(payload, "provider");
  const baseUrl = requiredString(payload, "base_url");
  if (!moduleKey || !channelId || !modelId || !provider || !baseUrl) {
    return invalidApiResponse("llm module resolution response missing required fields");
  }

  return {
    ok: true,
    module_key: moduleKey,
    channel_id: channelId,
    model_id: modelId,
    provider,
    base_url: baseUrl,
    supports_tools: Boolean(payload.supports_tools),
    supports_json: Boolean(payload.supports_json),
    settings: recordFromUnknown(payload.settings),
  };
}

async function decodeLLMModuleBindingsResponse(response: Response): Promise<LLMModuleBindingsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_BINDING_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("llm module bindings response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeLLMModuleBindingRecord(item)),
  };
}

async function decodeLLMModulesResponse(response: Response): Promise<LLMModulesSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_MODULE_REGISTRY_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("llm modules response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeLLMModuleRecord(item)),
  };
}

async function decodeLLMModuleBindingResponse(response: Response): Promise<LLMModuleBindingSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_BINDING_UPDATE_FAILED");
  }

  return {
    ok: true,
    ...decodeLLMModuleBindingRecord(payload),
  };
}

async function decodeLLMSettingsResponse(response: Response): Promise<LLMSettingsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_SETTINGS_QUERY_FAILED");
  }
  if (!Array.isArray(payload.modules) || !Array.isArray(payload.channels) || !Array.isArray(payload.tenant_bindings)) {
    return invalidApiResponse("llm settings response missing required arrays");
  }

  return {
    ok: true,
    modules: payload.modules.map((item) => decodeLLMModuleRecord(item)),
    channels: payload.channels.map((item) => decodeLLMChannelRecord(item)),
    tenant_bindings: payload.tenant_bindings.map((item) => decodeLLMModuleBindingRecord(item)),
  };
}

async function decodeLLMChannelsResponse(response: Response): Promise<LLMChannelsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_CATALOG_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("llm channels response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeLLMChannelRecord(item)),
  };
}

async function decodeLLMChannelResponse(response: Response): Promise<LLMChannelSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_CHANNEL_UPDATE_FAILED");
  }

  return {
    ok: true,
    ...decodeLLMChannelRecord(payload),
  };
}

async function decodeLLMChannelModelsResponse(response: Response): Promise<LLMChannelModelsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_CATALOG_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("llm channel models response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeLLMModelRecord(item)),
  };
}

async function decodeLLMModelSyncResponse(response: Response): Promise<LLMModelSyncSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_MODEL_SYNC_FAILED");
  }
  if (!Array.isArray(payload.models)) {
    return invalidApiResponse("llm model sync response missing models");
  }

  return {
    ok: true,
    channel: decodeLLMChannelRecord(payload.channel),
    models: payload.models.map((item) => decodeLLMModelRecord(item)),
  };
}

async function decodeLLMActivityResponse(response: Response): Promise<LLMActivitySummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_ACTIVITY_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("llm activity response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeLLMActivityRecord(item)),
  };
}

async function decodeLLMUsageResponse(response: Response): Promise<LLMUsageSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "LLM_ACTIVITY_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("llm usage response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeLLMUsageRecord(item)),
  };
}

async function decodeAssetListResponse(response: Response): Promise<AssetListSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ASSET_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("asset list response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeAssetRecord(item)),
  };
}

async function decodeWorldlineSavedPathsResponse(response: Response): Promise<WorldlineSavedPathsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("worldline saved path response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeWorldlineSavedPathRecord(item)),
  };
}

async function decodeWorldlineSavedPathResponse(response: Response): Promise<WorldlineSavedPathSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_SAVED_PATH_CREATE_FAILED");
  }
  return {
    ok: true,
    ...decodeWorldlineSavedPathRecord(payload),
  };
}

async function decodeWorldlineSessionsResponse(response: Response): Promise<WorldlineSessionsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_SESSION_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("worldline session response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeWorldlineSessionRecord(item)),
  };
}

async function decodeWorldlineSessionResponse(response: Response): Promise<WorldlineSessionSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_SESSION_QUERY_FAILED");
  }
  return {
    ok: true,
    ...decodeWorldlineSessionRecord(payload),
  };
}

async function decodeWorldlineSessionStartResponse(response: Response): Promise<WorldlineSessionStartSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_SESSION_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !workflowType || !status) {
    return invalidApiResponse("worldline session response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeWorldlineStepStartResponse(response: Response): Promise<WorldlineStepStartSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_STEP_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const sessionId = requiredString(payload, "session_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !sessionId || !workflowType || !status) {
    return invalidApiResponse("worldline step response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    session_id: sessionId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeWorldlineTimelineResponse(response: Response): Promise<WorldlineTimelineSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_TIMELINE_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("worldline timeline response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeWorldlineTimelineEventRecord(item)),
  };
}

async function decodeWorldlineEventsResponse(response: Response): Promise<WorldlineEventsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_EVENT_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("worldline events response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeWorldlineEventRecord(item)),
  };
}

async function decodeWorldlineEventResponse(response: Response): Promise<WorldlineEventSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_EVENT_ADOPTION_FAILED");
  }
  return {
    ok: true,
    ...decodeWorldlineEventRecord(payload),
  };
}

async function decodeWorldlineVariableResponse(response: Response): Promise<WorldlineVariableSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_VARIABLE_INJECTION_FAILED");
  }
  return {
    ok: true,
    ...decodeWorldlineVariableRecord(payload),
  };
}

async function decodeWorldlinePreparationResponse(
  response: Response,
  fallbackCode: string,
): Promise<WorldlinePreparationSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, fallbackCode);
  }
  return {
    ok: true,
    ...decodeWorldlinePreparationRecord(payload),
  };
}

async function decodeWorldlinePreparedAgentsResponse(response: Response): Promise<WorldlinePreparedAgentsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "WORLDLINE_PREPARED_AGENTS_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("worldline prepared agents response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeWorldlinePreparedAgentRecord(item)),
  };
}

async function decodeCharacterInteractionsResponse(response: Response): Promise<CharacterInteractionsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "CHARACTER_INTERACTION_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("character interactions response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeCharacterInteractionRecord(item)),
  };
}

async function decodeCharacterInteractionDetailResponse(response: Response): Promise<CharacterInteractionDetailSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "CHARACTER_INTERACTION_QUERY_FAILED");
  }

  return {
    ok: true,
    ...decodeCharacterInteractionRecord(payload),
    turns: arrayFromUnknown(payload.turns).map((item) => decodeCharacterInteractionTurnRecord(item)),
  };
}

async function decodeCharacterInteractionResponse(
  response: Response,
  fallbackCode: string,
): Promise<CharacterInteractionSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, fallbackCode);
  }

  return {
    ok: true,
    ...decodeCharacterInteractionRecord(payload),
  };
}

async function decodeCharacterInteractionTurnResponse(response: Response): Promise<CharacterInteractionTurnSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "CHARACTER_INTERACTION_TURN_CREATE_FAILED");
  }

  return {
    ok: true,
    ...decodeCharacterInteractionTurnRecord(payload),
  };
}

async function decodeCharacterInteractionTurnsResponse(response: Response): Promise<CharacterInteractionTurnsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "CHARACTER_INTERACTION_TURN_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("character interaction turns response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeCharacterInteractionTurnRecord(item)),
  };
}

async function decodeCharacterInteractionEventsResponse(response: Response): Promise<CharacterInteractionEventsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "CHARACTER_INTERACTION_EVENTS_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("character interaction events response missing items");
  }

  return {
    ok: true,
    interaction_id: requiredString(payload, "interaction_id"),
    after_event_id: requiredString(payload, "after_event_id"),
    items: payload.items.map((item) => decodeCharacterInteractionEventRecord(item)),
  };
}

async function decodeCharacterInteractionChapterDraftResponse(
  response: Response,
): Promise<CharacterInteractionChapterDraftSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "CHARACTER_INTERACTION_CHAPTER_DRAFT_FAILED");
  }

  return {
    ok: true,
    interaction_id: requiredString(payload, "interaction_id"),
    run_id: requiredString(payload, "run_id"),
    trace_id: requiredString(payload, "trace_id"),
    project_id: requiredString(payload, "project_id"),
    workflow_type: requiredString(payload, "workflow_type"),
    status: requiredString(payload, "status"),
  };
}

async function decodeAssetFacetsResponse(response: Response): Promise<AssetFacetsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ASSET_QUERY_FAILED");
  }

  return {
    ok: true,
    asset_types: arrayFromUnknown(payload.asset_types).map((item) => decodeAssetFacetBucket(item)),
    categories: arrayFromUnknown(payload.categories).map((item) => decodeAssetFacetBucket(item)),
    lifecycles: arrayFromUnknown(payload.lifecycles).map((item) => decodeAssetFacetBucket(item)),
    sources: arrayFromUnknown(payload.sources).map((item) => decodeAssetFacetBucket(item)),
    tags: arrayFromUnknown(payload.tags).map((item) => decodeAssetFacetBucket(item)),
  };
}

async function decodeAssetSearchResponse(response: Response): Promise<AssetSearchSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ASSET_SEARCH_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("asset search response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeAssetSearchRecord(item)),
  };
}

async function decodeArchiveMemoryResponse(response: Response): Promise<ArchiveMemorySummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ARCHIVE_MEMORY_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("archive memory response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeArchiveMemoryRecord(item)),
  };
}

async function decodeArchiveMemoryEventsResponse(response: Response): Promise<ArchiveMemoryEventsSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ARCHIVE_MEMORY_QUERY_FAILED");
  }
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("archive memory event response missing items");
  }

  return {
    ok: true,
    items: payload.items.map((item) => decodeArchiveMemoryEventRecord(item)),
  };
}

async function decodeArchiveMemoryReviewResponse(
  response: Response,
  fallbackCode: string,
): Promise<ArchiveMemoryReviewSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, fallbackCode);
  }

  return {
    ok: true,
    ...decodeArchiveMemoryRecord(payload),
  };
}

async function decodeAssetResponse(response: Response, fallbackCode: string): Promise<AssetSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, fallbackCode);
  }

  return {
    ok: true,
    ...decodeAssetRecord(payload),
  };
}

async function decodeAssetDeleteResponse(response: Response): Promise<AssetDeleteSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ASSET_MUTATION_FAILED");
  }

  return {
    ok: true,
    asset_id: requiredString(payload, "asset_id"),
    project_id: requiredString(payload, "project_id"),
    deleted: Boolean(payload.deleted),
  };
}

async function decodeAssetBulkActionResponse(response: Response): Promise<AssetBulkActionSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ASSET_BULK_ACTION_FAILED");
  }

  return {
    ok: true,
    project_id: requiredString(payload, "project_id"),
    action: requiredString(payload, "action"),
    status: requiredString(payload, "status"),
    matched_count: numberFromUnknown(payload.matched_count),
    updated_count: numberFromUnknown(payload.updated_count),
  };
}

async function decodeAssetIngestionResponse(response: Response): Promise<AssetIngestionSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ASSET_INGESTION_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !workflowType || !status) {
    return invalidApiResponse("asset ingestion response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeAssetReindexResponse(response: Response): Promise<AssetReindexSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "ASSET_REINDEX_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !workflowType || !status) {
    return invalidApiResponse("asset reindex response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeStyleExtractionResponse(response: Response): Promise<StyleExtractionSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STYLE_EXTRACTION_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !workflowType || !status) {
    return invalidApiResponse("style extraction response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeStoryGraphBuildResponse(response: Response): Promise<StoryGraphBuildSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STORY_GRAPH_BUILD_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !workflowType || !status) {
    return invalidApiResponse("story graph build response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeStoryGraphBondGenerationResponse(
  response: Response,
): Promise<StoryGraphBondGenerationSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STORY_GRAPH_BOND_START_FAILED");
  }

  const runId = requiredString(payload, "run_id");
  const projectId = requiredString(payload, "project_id");
  const workflowType = requiredString(payload, "workflow_type");
  const status = requiredString(payload, "status");
  if (!runId || !projectId || !workflowType || !status) {
    return invalidApiResponse("story graph bond generation response missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    project_id: projectId,
    workflow_type: workflowType,
    status,
  };
}

async function decodeStoryGraphCurrentResponse(response: Response): Promise<StoryGraphCurrentSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STORY_GRAPH_QUERY_FAILED");
  }

  const graphId = requiredString(payload, "graph_id");
  const projectId = requiredString(payload, "project_id");
  const status = requiredString(payload, "status");
  if (!graphId || !projectId || !status) {
    return invalidApiResponse("story graph current response missing required fields");
  }
  return {
    ok: true,
    graph_id: graphId,
    project_id: projectId,
    version: numberFromUnknown(payload.version),
    status,
    build_run_id: requiredString(payload, "build_run_id"),
    source_version_hash: requiredString(payload, "source_version_hash"),
    node_count: numberFromUnknown(payload.node_count),
    edge_count: numberFromUnknown(payload.edge_count),
    created_at: requiredString(payload, "created_at"),
    updated_at: requiredString(payload, "updated_at"),
  };
}

async function decodeStoryGraphViewResponse(response: Response): Promise<StoryGraphViewSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STORY_GRAPH_QUERY_FAILED");
  }

  const viewId = requiredString(payload, "view_id");
  const graphId = requiredString(payload, "graph_id");
  const projectId = requiredString(payload, "project_id");
  if (!viewId || !graphId || !projectId || !Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
    return invalidApiResponse("story graph view response missing required fields");
  }
  return {
    ok: true,
    view_id: viewId,
    graph_id: graphId,
    project_id: projectId,
    limit: numberFromUnknown(payload.limit),
    include_edges: Boolean(payload.include_edges),
    nodes: payload.nodes.map((node) => decodeStoryGraphNodeRecord(node)),
    edges: payload.edges.map((edge) => decodeStoryGraphEdgeRecord(edge)),
  };
}

async function decodeStoryGraphEvidenceResponse(response: Response): Promise<StoryGraphEvidenceSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STORY_GRAPH_QUERY_FAILED");
  }

  const graphId = requiredString(payload, "graph_id");
  const projectId = requiredString(payload, "project_id");
  const ownerType = requiredString(payload, "owner_type");
  const ownerId = requiredString(payload, "owner_id");
  if (!graphId || !projectId || !ownerType || !ownerId || !Array.isArray(payload.items)) {
    return invalidApiResponse("story graph evidence response missing required fields");
  }
  return {
    ok: true,
    graph_id: graphId,
    project_id: projectId,
    owner_type: ownerType,
    owner_id: ownerId,
    limit: numberFromUnknown(payload.limit),
    items: payload.items.map((item) => decodeStoryGraphEvidenceRecord(item)),
  };
}

async function decodeStoryGraphLayoutResponse(response: Response): Promise<StoryGraphLayoutSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STORY_GRAPH_QUERY_FAILED");
  }

  const graphId = requiredString(payload, "graph_id");
  const projectId = requiredString(payload, "project_id");
  const viewId = requiredString(payload, "view_id");
  if (!graphId || !projectId || !viewId) {
    return invalidApiResponse("story graph layout response missing required fields");
  }
  return {
    ok: true,
    graph_id: graphId,
    project_id: projectId,
    view_id: viewId,
    layout: recordFromUnknown(payload.layout),
    created_at: requiredString(payload, "created_at"),
    updated_at: requiredString(payload, "updated_at"),
  };
}

async function decodeStoryGraphClustersResponse(response: Response): Promise<StoryGraphClustersSummary> {
  const payload = await readLLMPayload(response);
  if (isApiFailure(payload)) {
    return payload;
  }
  if (!response.ok) {
    return decodeError(payload, response.status, "STORY_GRAPH_QUERY_FAILED");
  }

  const graphId = requiredString(payload, "graph_id");
  const projectId = requiredString(payload, "project_id");
  if (!graphId || !projectId || !Array.isArray(payload.items)) {
    return invalidApiResponse("story graph clusters response missing required fields");
  }
  return {
    ok: true,
    graph_id: graphId,
    project_id: projectId,
    limit: numberFromUnknown(payload.limit),
    items: payload.items.map((item) => decodeStoryGraphClusterRecord(item)),
  };
}

function decodeTraceItems(
  payload: Record<string, unknown>,
  projectId: string,
  traceId: string,
  includeFull: boolean,
): AgentTraceEventsSummary {
  if (!Array.isArray(payload.items)) {
    return invalidApiResponse("agent trace response missing items");
  }

  return {
    ok: true,
    project_id: projectId,
    trace_id: traceId,
    include_full: includeFull,
    items: payload.items.map((item) => decodeTraceEvent(item)),
  };
}

function decodeSourceFileRecord(item: unknown): SourceFileRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    file_id: requiredString(value, "file_id"),
    upload_id: requiredString(value, "upload_id"),
    project_id: requiredString(value, "project_id"),
    filename: requiredString(value, "filename"),
    mime_type: requiredString(value, "mime_type"),
    size_bytes: numberFromUnknown(value.size_bytes),
    sha256: requiredString(value, "sha256"),
    purpose: requiredString(value, "purpose"),
    parse_status: requiredString(value, "parse_status"),
    created_at: requiredString(value, "created_at"),
  };
}

function decodeProjectReadinessSnapshot(item: unknown): ProjectReadinessSnapshot {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    project_readiness_snapshot_id: requiredString(value, "project_readiness_snapshot_id"),
    project_id: requiredString(value, "project_id"),
    run_id: requiredString(value, "run_id"),
    ready_asset_count: numberFromUnknown(value.ready_asset_count),
    ready_entity_count: numberFromUnknown(value.ready_entity_count),
    ready_relationship_count: numberFromUnknown(value.ready_relationship_count),
    ready_world_rule_count: numberFromUnknown(value.ready_world_rule_count),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeProjectOverviewRecord(item: unknown): ProjectOverviewRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    project_id: requiredString(value, "project_id"),
    status: requiredString(value, "status"),
    source_file_count: numberFromUnknown(value.source_file_count),
    seed_run_count: numberFromUnknown(value.seed_run_count),
    active_workflow_run_id: requiredString(value, "active_workflow_run_id"),
    active_workflow_type: requiredString(value, "active_workflow_type"),
    active_workflow_status: requiredString(value, "active_workflow_status"),
    readiness_snapshot_id: requiredString(value, "readiness_snapshot_id"),
    readiness_run_id: requiredString(value, "readiness_run_id"),
    ready_asset_count: numberFromUnknown(value.ready_asset_count),
    ready_entity_count: numberFromUnknown(value.ready_entity_count),
    ready_relationship_count: numberFromUnknown(value.ready_relationship_count),
    ready_world_rule_count: numberFromUnknown(value.ready_world_rule_count),
    asset_count: numberFromUnknown(value.asset_count),
    graph_node_count: numberFromUnknown(value.graph_node_count),
    graph_edge_count: numberFromUnknown(value.graph_edge_count),
    worldline_session_count: numberFromUnknown(value.worldline_session_count),
    worldline_event_count: numberFromUnknown(value.worldline_event_count),
    character_interaction_count: numberFromUnknown(value.character_interaction_count),
    writer_run_count: numberFromUnknown(value.writer_run_count),
    llm_activity_count: numberFromUnknown(value.llm_activity_count),
    llm_token_count: numberFromUnknown(value.llm_token_count),
    llm_enabled_channel_count: numberFromUnknown(value.llm_enabled_channel_count),
    llm_bound_module_count: numberFromUnknown(value.llm_bound_module_count),
    llm_missing_core_module_count: numberFromUnknown(value.llm_missing_core_module_count),
    llm_sync_ok_channel_count: numberFromUnknown(value.llm_sync_ok_channel_count),
    llm_sync_failed_channel_count: numberFromUnknown(value.llm_sync_failed_channel_count),
    llm_sync_pending_channel_count: numberFromUnknown(value.llm_sync_pending_channel_count),
    llm_latest_sync_at: requiredString(value, "llm_latest_sync_at"),
    latest_failed_workflow_run_id: requiredString(value, "latest_failed_workflow_run_id"),
    latest_failed_workflow_type: requiredString(value, "latest_failed_workflow_type"),
    latest_failed_workflow_error_code: requiredString(value, "latest_failed_workflow_error_code"),
    latest_failed_workflow_updated_at: requiredString(value, "latest_failed_workflow_updated_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeWorkflowRunRecord(item: unknown): WorkflowRunSummary {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  const runId = requiredString(value, "run_id");
  const workflowType = requiredString(value, "workflow_type");
  const projectId = requiredString(value, "project_id");
  const status = requiredString(value, "status");
  if (!runId || !workflowType || !projectId || !status) {
    return invalidApiResponse("workflow run item missing required fields");
  }
  return {
    ok: true,
    run_id: runId,
    workflow_type: workflowType,
    project_id: projectId,
    status,
    progress: numberFromUnknown(value.progress),
    message: requiredString(value, "message"),
    error_code: requiredString(value, "error_code"),
    error_message: requiredString(value, "error_message"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeTraceEvent(item: unknown): AgentTraceEvent {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  const payload = value.payload && typeof value.payload === "object" && !Array.isArray(value.payload)
    ? (value.payload as Record<string, unknown>)
    : {};

  return {
    event_id: requiredString(value, "event_id"),
    trace_id: requiredString(value, "trace_id"),
    event_order: typeof value.event_order === "number" ? value.event_order : 0,
    event_type: requiredString(value, "event_type"),
    payload,
    redaction_level: requiredString(value, "redaction_level"),
    created_at: requiredString(value, "created_at"),
  };
}

function decodeWriterRunEvent(item: unknown): WriterRunEvent {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  const payload = value.payload && typeof value.payload === "object" && !Array.isArray(value.payload)
    ? (value.payload as Record<string, unknown>)
    : {};

  return {
    event_id: requiredString(value, "event_id"),
    run_id: requiredString(value, "run_id"),
    project_id: requiredString(value, "project_id"),
    sequence: numberFromUnknown(value.sequence),
    event_type: requiredString(value, "event_type"),
    payload,
    created_at: requiredString(value, "created_at"),
  };
}

function decodeManuscriptBlockMetadata(item: unknown): ManuscriptBlockMetadata {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    block_id: requiredString(value, "block_id"),
    chapter_id: requiredString(value, "chapter_id"),
    source_draft_id: requiredString(value, "source_draft_id"),
    block_order: numberFromUnknown(value.block_order),
    status: requiredString(value, "status"),
    word_count: numberFromUnknown(value.word_count),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeManuscriptExportManifestBlock(item: unknown): ManuscriptExportManifestBlock {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    block_id: requiredString(value, "block_id"),
    block_order: numberFromUnknown(value.block_order),
    word_count: numberFromUnknown(value.word_count),
  };
}

function decodeWorkflowRunEvent(item: unknown): WorkflowRunEvent {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  const payload = value.payload && typeof value.payload === "object" && !Array.isArray(value.payload)
    ? (value.payload as Record<string, unknown>)
    : {};

  return {
    event_id: requiredString(value, "event_id"),
    run_id: requiredString(value, "run_id"),
    project_id: requiredString(value, "project_id"),
    sequence: numberFromUnknown(value.sequence),
    event_type: requiredString(value, "event_type"),
    payload,
    created_at: requiredString(value, "created_at"),
  };
}

function decodeLLMActivityRecord(item: unknown): LLMActivityRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    activity_id: requiredString(value, "activity_id"),
    project_id: requiredString(value, "project_id"),
    run_id: requiredString(value, "run_id"),
    module_key: requiredString(value, "module_key"),
    channel_id: requiredString(value, "channel_id"),
    model_id: requiredString(value, "model_id"),
    status: requiredString(value, "status"),
    prompt_tokens: numberFromUnknown(value.prompt_tokens),
    completion_tokens: numberFromUnknown(value.completion_tokens),
    latency_ms: numberFromUnknown(value.latency_ms),
    cost_estimate: numberFromUnknown(value.cost_estimate),
    error: value.error ? recordFromUnknown(value.error) : null,
    created_at: requiredString(value, "created_at"),
  };
}

function decodeLLMModuleBindingRecord(item: unknown): LLMModuleBindingRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    module_key: requiredString(value, "module_key"),
    scope: requiredString(value, "scope"),
    channel_id: requiredString(value, "channel_id"),
    channel_name: requiredString(value, "channel_name"),
    model_id: requiredString(value, "model_id"),
    provider: requiredString(value, "provider"),
    base_url: requiredString(value, "base_url"),
    supports_tools: Boolean(value.supports_tools),
    supports_json: Boolean(value.supports_json),
    settings: recordFromUnknown(value.settings),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeLLMModuleRecord(item: unknown): LLMModuleRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    module_key: requiredString(value, "module_key"),
    group: requiredString(value, "group"),
    label: requiredString(value, "label"),
    description: requiredString(value, "description"),
  };
}

function decodeLLMChannelRecord(item: unknown): LLMChannelRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    channel_id: requiredString(value, "channel_id"),
    name: requiredString(value, "name"),
    provider: requiredString(value, "provider"),
    base_url: requiredString(value, "base_url"),
    max_concurrency: numberFromUnknown(value.max_concurrency),
    enabled: Boolean(value.enabled),
    last_sync_at: requiredString(value, "last_sync_at"),
    last_sync_status: requiredString(value, "last_sync_status"),
    scope: requiredString(value, "scope"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeLLMModelRecord(item: unknown): LLMModelRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    model_id: requiredString(value, "model_id"),
    owned_by: requiredString(value, "owned_by"),
    context_window: numberFromUnknown(value.context_window),
    supports_tools: Boolean(value.supports_tools),
    supports_json: Boolean(value.supports_json),
    input_cost: numberFromUnknown(value.input_cost),
    output_cost: numberFromUnknown(value.output_cost),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeLLMUsageRecord(item: unknown): LLMUsageRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    usage_type: requiredString(value, "usage_type"),
    quantity: numberFromUnknown(value.quantity),
    unit: requiredString(value, "unit"),
    module_key: requiredString(value, "module_key"),
    run_id: requiredString(value, "run_id"),
  };
}

function decodeAssetRecord(item: unknown): AssetRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    asset_id: requiredString(value, "asset_id"),
    project_id: requiredString(value, "project_id"),
    scope: requiredString(value, "scope"),
    asset_type: requiredString(value, "asset_type"),
    category: requiredString(value, "category"),
    lifecycle: requiredString(value, "lifecycle"),
    title: requiredString(value, "title"),
    summary: requiredString(value, "summary"),
    source_kind: requiredString(value, "source_kind"),
    source_ref: requiredString(value, "source_ref"),
    enabled: Boolean(value.enabled),
    pinned: Boolean(value.pinned),
    tags: stringArrayFromUnknown(value.tags),
    payload: recordFromUnknown(value.payload),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeWorldlineSavedPathRecord(item: unknown): WorldlineSavedPathRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    path_id: requiredString(value, "path_id"),
    session_id: requiredString(value, "session_id"),
    project_id: requiredString(value, "project_id"),
    title: requiredString(value, "title"),
    summary: requiredString(value, "summary"),
    lifecycle: requiredString(value, "lifecycle"),
    selected_event_ids: stringArrayFromUnknown(value.selected_event_ids),
    writer_instruction: requiredString(value, "writer_instruction"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeWorldlineSessionRecord(item: unknown): WorldlineSessionRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    session_id: requiredString(value, "session_id"),
    run_id: requiredString(value, "run_id"),
    project_id: requiredString(value, "project_id"),
    status: requiredString(value, "status"),
    lifecycle: requiredString(value, "lifecycle"),
    goal_summary: requiredString(value, "goal_summary"),
    anchor_path_id: requiredString(value, "anchor_path_id"),
    created_by: requiredString(value, "created_by"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeWorldlineTimelineEventRecord(item: unknown): WorldlineTimelineEventRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    event_id: requiredString(value, "event_id"),
    session_id: requiredString(value, "session_id"),
    run_id: requiredString(value, "run_id"),
    project_id: requiredString(value, "project_id"),
    event_type: requiredString(value, "event_type"),
    sequence: numberFromUnknown(value.sequence),
    status: requiredString(value, "status"),
    lifecycle: requiredString(value, "lifecycle"),
    title: requiredString(value, "title"),
    summary: requiredString(value, "summary"),
    kind: requiredString(value, "kind"),
    created_at: requiredString(value, "created_at"),
  };
}

function decodeWorldlineEventRecord(item: unknown): WorldlineEventRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    event_id: requiredString(value, "event_id"),
    session_id: requiredString(value, "session_id"),
    project_id: requiredString(value, "project_id"),
    step: numberFromUnknown(value.step),
    title: requiredString(value, "title"),
    summary: requiredString(value, "summary"),
    kind: requiredString(value, "kind"),
    status: requiredString(value, "status"),
    lifecycle: requiredString(value, "lifecycle"),
    confidence: requiredString(value, "confidence"),
    involved_agent_ids: stringArrayFromUnknown(value.involved_agent_ids),
    state_changes: recordFromUnknown(value.state_changes),
    source_run_id: requiredString(value, "source_run_id"),
    created_by: requiredString(value, "created_by"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeWorldlineVariableRecord(item: unknown): WorldlineVariableRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    variable_id: requiredString(value, "variable_id"),
    session_id: requiredString(value, "session_id"),
    project_id: requiredString(value, "project_id"),
    name: requiredString(value, "name"),
    description: requiredString(value, "description"),
    impact_axis: requiredString(value, "impact_axis"),
    locked: Boolean(value.locked),
    source: requiredString(value, "source"),
    created_by: requiredString(value, "created_by"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeWorldlinePreparationRecord(item: unknown): WorldlinePreparationRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    prepare_id: requiredString(value, "prepare_id"),
    run_id: requiredString(value, "run_id"),
    project_id: requiredString(value, "project_id"),
    workflow_type: requiredString(value, "workflow_type"),
    status: requiredString(value, "status"),
    lifecycle: requiredString(value, "lifecycle"),
    goal_summary: requiredString(value, "goal_summary"),
    anchor_path_id: requiredString(value, "anchor_path_id"),
    created_by: requiredString(value, "created_by"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeWorldlinePreparedAgentRecord(item: unknown): WorldlinePreparedAgentRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    agent_id: requiredString(value, "agent_id"),
    prepare_id: requiredString(value, "prepare_id"),
    project_id: requiredString(value, "project_id"),
    display_name: requiredString(value, "display_name"),
    role: requiredString(value, "role"),
    status: requiredString(value, "status"),
    source_asset_id: requiredString(value, "source_asset_id"),
    summary: requiredString(value, "summary"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeCharacterInteractionRecord(item: unknown): CharacterInteractionRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    interaction_id: requiredString(value, "interaction_id"),
    project_id: requiredString(value, "project_id"),
    worldline_session_id: requiredString(value, "worldline_session_id"),
    anchor_type: requiredString(value, "anchor_type"),
    anchor_id: requiredString(value, "anchor_id"),
    pov_agent_id: requiredString(value, "pov_agent_id"),
    mode: requiredString(value, "mode"),
    status: requiredString(value, "status"),
    title: requiredString(value, "title"),
    summary: requiredString(value, "summary"),
    metadata: recordFromUnknown(value.metadata),
    created_by: requiredString(value, "created_by"),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeCharacterInteractionTurnRecord(item: unknown): CharacterInteractionTurnRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    turn_id: requiredString(value, "turn_id"),
    interaction_id: requiredString(value, "interaction_id"),
    project_id: requiredString(value, "project_id"),
    turn_order: numberFromUnknown(value.turn_order),
    actor_type: requiredString(value, "actor_type"),
    actor_id: requiredString(value, "actor_id"),
    turn_kind: requiredString(value, "turn_kind"),
    summary: requiredString(value, "summary"),
    action: recordFromUnknown(value.action),
    world_state_delta: recordFromUnknown(value.world_state_delta),
    trace_id: requiredString(value, "trace_id"),
    created_by: requiredString(value, "created_by"),
    created_at: requiredString(value, "created_at"),
  };
}

function decodeCharacterInteractionEventRecord(item: unknown): CharacterInteractionEventRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    event_id: requiredString(value, "event_id"),
    interaction_id: requiredString(value, "interaction_id"),
    sequence: numberFromUnknown(value.sequence),
    event_type: requiredString(value, "event_type"),
    payload: recordFromUnknown(value.payload),
    created_at: requiredString(value, "created_at"),
  };
}

function decodeAssetFacetBucket(item: unknown): AssetFacetBucket {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    value: requiredString(value, "value"),
    count: numberFromUnknown(value.count),
  };
}

function decodeAssetSearchRecord(item: unknown): AssetSearchRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    search_document_id: requiredString(value, "search_document_id"),
    source: requiredString(value, "source"),
    source_ref: requiredString(value, "source_ref"),
    project_id: requiredString(value, "project_id"),
    entity_type: requiredString(value, "entity_type"),
    title: requiredString(value, "title"),
    tags: stringArrayFromUnknown(value.tags),
    payload: recordFromUnknown(value.payload),
    version: decodeAssetSearchVersion(value.version),
    collections: arrayFromUnknown(value.collections).map((collection) => decodeAssetSearchCollection(collection)),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeAssetSearchVersion(item: unknown): AssetSearchVersion {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    count: numberFromUnknown(value.count),
    latest_version: numberFromUnknown(value.latest_version),
    latest_version_id: typeof value.latest_version_id === "string" ? value.latest_version_id : "",
  };
}

function decodeAssetSearchCollection(item: unknown): AssetSearchCollection {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    collection_id: requiredString(value, "collection_id"),
    title: requiredString(value, "title"),
    lifecycle: requiredString(value, "lifecycle"),
  };
}

function decodeArchiveMemoryRecord(item: unknown): ArchiveMemoryRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    memory_id: requiredString(value, "memory_id"),
    asset_id: requiredString(value, "asset_id"),
    project_id: requiredString(value, "project_id"),
    memory_type: requiredString(value, "memory_type"),
    status: requiredString(value, "status"),
    summary: requiredString(value, "summary"),
    payload: recordFromUnknown(value.payload),
    source_kind: requiredString(value, "source_kind"),
    source_ref: requiredString(value, "source_ref"),
    enabled: Boolean(value.enabled),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeArchiveMemoryEventRecord(item: unknown): ArchiveMemoryEventRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    event_id: requiredString(value, "event_id"),
    memory_id: requiredString(value, "memory_id"),
    asset_id: requiredString(value, "asset_id"),
    project_id: requiredString(value, "project_id"),
    event_type: requiredString(value, "event_type"),
    status: requiredString(value, "status"),
    payload: recordFromUnknown(value.payload),
    actor_id: requiredString(value, "actor_id"),
    created_at: requiredString(value, "created_at"),
  };
}

function decodeStoryGraphNodeRecord(item: unknown): StoryGraphNodeRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    node_id: requiredString(value, "node_id"),
    graph_id: requiredString(value, "graph_id"),
    project_id: requiredString(value, "project_id"),
    node_type: requiredString(value, "node_type"),
    title: requiredString(value, "title"),
    summary: requiredString(value, "summary"),
    lifecycle: requiredString(value, "lifecycle"),
    importance: numberFromUnknown(value.importance),
    cluster_id: requiredString(value, "cluster_id"),
    attributes: recordFromUnknown(value.attributes),
    evidence_count: numberFromUnknown(value.evidence_count),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeTenantMembershipSummaries(items: unknown[]): TenantMembershipSummary[] | null {
  const summaries = items.map((item) => decodeTenantMembershipSummary(item));
  return summaries.every((item): item is TenantMembershipSummary => item !== null) ? summaries : null;
}

function decodeProjectMembershipSummaries(items: unknown[]): ProjectMembershipSummary[] | null {
  const summaries = items.map((item) => decodeProjectMembershipSummary(item));
  return summaries.every((item): item is ProjectMembershipSummary => item !== null) ? summaries : null;
}

function decodeTenantMembershipSummary(item: unknown): TenantMembershipSummary | null {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  const tenantId = requiredString(value, "tenant_id");
  const tenantName = requiredString(value, "name");
  const role = requiredString(value, "role");
  const status = requiredString(value, "status");
  if (!tenantId || !tenantName || !role || !status) {
    return null;
  }
  return {
    tenant_id: tenantId,
    name: tenantName,
    role,
    status,
  };
}

function decodeProjectMembershipSummary(item: unknown): ProjectMembershipSummary | null {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  const tenantId = requiredString(value, "tenant_id");
  const projectId = requiredString(value, "project_id");
  const projectName = requiredString(value, "name");
  const role = requiredString(value, "role");
  const status = requiredString(value, "status");
  if (!tenantId || !projectId || !projectName || !role || !status) {
    return null;
  }
  return {
    tenant_id: tenantId,
    project_id: projectId,
    name: projectName,
    role,
    status,
  };
}

function decodeStoryGraphEdgeRecord(item: unknown): StoryGraphEdgeRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    edge_id: requiredString(value, "edge_id"),
    graph_id: requiredString(value, "graph_id"),
    project_id: requiredString(value, "project_id"),
    source_node_id: requiredString(value, "source_node_id"),
    target_node_id: requiredString(value, "target_node_id"),
    edge_type: requiredString(value, "edge_type"),
    label: requiredString(value, "label"),
    summary: requiredString(value, "summary"),
    weight: numberFromUnknown(value.weight),
    lifecycle: requiredString(value, "lifecycle"),
    attributes: recordFromUnknown(value.attributes),
    evidence_count: numberFromUnknown(value.evidence_count),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeStoryGraphEvidenceRecord(item: unknown): StoryGraphEvidenceRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    evidence_id: requiredString(value, "evidence_id"),
    graph_id: requiredString(value, "graph_id"),
    project_id: requiredString(value, "project_id"),
    owner_type: requiredString(value, "owner_type"),
    owner_id: requiredString(value, "owner_id"),
    source_type: requiredString(value, "source_type"),
    source_id: requiredString(value, "source_id"),
    chapter_id: requiredString(value, "chapter_id"),
    segment_id: requiredString(value, "segment_id"),
    confidence: numberFromUnknown(value.confidence),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function decodeStoryGraphClusterRecord(item: unknown): StoryGraphClusterRecord {
  const value = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
  return {
    cluster_id: requiredString(value, "cluster_id"),
    graph_id: requiredString(value, "graph_id"),
    project_id: requiredString(value, "project_id"),
    cluster_key: requiredString(value, "cluster_key"),
    title: requiredString(value, "title"),
    summary: requiredString(value, "summary"),
    node_count: numberFromUnknown(value.node_count),
    payload: recordFromUnknown(value.payload),
    created_at: requiredString(value, "created_at"),
    updated_at: requiredString(value, "updated_at"),
  };
}

function contextHeaders(input: ApiContext) {
  const headers: Record<string, string> = {
    "X-Tenant-Id": input.tenantId,
  };
  const sessionCookie = input.sessionCookie?.trim();
  const actorUserId = input.actorUserId?.trim();

  if (sessionCookie) {
    headers.Cookie = `mirofish_session=${sessionCookie}`;
  } else if (actorUserId) {
    headers["X-User-Id"] = actorUserId;
  }

  return headers;
}

function addTelemetryFilters(url: URL, input: { moduleKey?: string; runId?: string }) {
  if (input.moduleKey) {
    url.searchParams.set("module_key", input.moduleKey);
  }
  if (input.runId) {
    url.searchParams.set("run_id", input.runId);
  }
}

function decodeError(payload: Record<string, unknown>, status: number, fallbackCode: string): ApiFailure {
  const error = payload.error as { code?: string; message?: string; request_id?: string } | undefined;
  return {
    ok: false,
    code: error?.code ?? fallbackCode,
    message: error?.message ?? `HTTP ${status}`,
    request_id: error?.request_id ?? "",
  };
}

function invalidApiResponse(message: string): ApiFailure {
  return {
    ok: false,
    code: "INVALID_API_RESPONSE",
    message,
    request_id: "",
  };
}

async function readLLMPayload(response: Response): Promise<Record<string, unknown> | ApiFailure> {
  try {
    const payload = (await response.json()) as unknown;
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      return payload as Record<string, unknown>;
    }
  } catch {
    return invalidApiResponse(`API returned non-JSON response (HTTP ${response.status})`);
  }
  return invalidApiResponse(`API returned malformed JSON response (HTTP ${response.status})`);
}

function isApiFailure(payload: Record<string, unknown> | ApiFailure): payload is ApiFailure {
  return payload.ok === false;
}

function networkFailure(error: unknown, code: string): ApiFailure {
  return {
    ok: false,
    code,
    message: error instanceof Error ? error.message : "network request failed",
    request_id: "",
  };
}

function requiredString(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayFromUnknown(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function requiredArray(payload: Record<string, unknown>, key: string): unknown[] | null {
  const value = payload[key];
  return Array.isArray(value) ? value : null;
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function numberFromUnknown(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
