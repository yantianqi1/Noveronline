package projectoverview

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
)

type GetProjectOverviewInput struct {
	TenantID  string
	ProjectID string
}

type Overview struct {
	ProjectID                     string `json:"project_id"`
	Status                        string `json:"status"`
	SourceFileCount               int    `json:"source_file_count"`
	SeedRunCount                  int    `json:"seed_run_count"`
	ActiveWorkflowRunID           string `json:"active_workflow_run_id"`
	ActiveWorkflowType            string `json:"active_workflow_type"`
	ActiveWorkflowStatus          string `json:"active_workflow_status"`
	ReadinessSnapshotID           string `json:"readiness_snapshot_id"`
	ReadinessRunID                string `json:"readiness_run_id"`
	ReadyAssetCount               int    `json:"ready_asset_count"`
	ReadyEntityCount              int    `json:"ready_entity_count"`
	ReadyRelationshipCount        int    `json:"ready_relationship_count"`
	ReadyWorldRuleCount           int    `json:"ready_world_rule_count"`
	TotalSegmentCount             int    `json:"total_segment_count"`
	SucceededSegmentCount         int    `json:"succeeded_segment_count"`
	FailedSegmentIDs              []string `json:"failed_segment_ids"`
	AssetCount                    int    `json:"asset_count"`
	GraphNodeCount                int    `json:"graph_node_count"`
	GraphEdgeCount                int    `json:"graph_edge_count"`
	WorldlineSessionCount         int    `json:"worldline_session_count"`
	WorldlineEventCount           int    `json:"worldline_event_count"`
	CharacterInteractionCount     int    `json:"character_interaction_count"`
	WriterRunCount                int    `json:"writer_run_count"`
	LLMActivityCount              int    `json:"llm_activity_count"`
	LLMTokenCount                 int    `json:"llm_token_count"`
	LLMEnabledChannelCount        int    `json:"llm_enabled_channel_count"`
	LLMBoundModuleCount           int    `json:"llm_bound_module_count"`
	LLMMissingCoreModuleCount     int    `json:"llm_missing_core_module_count"`
	LLMSyncOKChannelCount         int    `json:"llm_sync_ok_channel_count"`
	LLMSyncFailedChannelCount     int    `json:"llm_sync_failed_channel_count"`
	LLMSyncPendingChannelCount    int    `json:"llm_sync_pending_channel_count"`
	LLMLatestSyncAt               string `json:"llm_latest_sync_at"`
	LLMHasQuotaPolicy             bool   `json:"llm_has_quota_policy"`
	LatestFailedWorkflowRunID     string `json:"latest_failed_workflow_run_id"`
	LatestFailedWorkflowType      string `json:"latest_failed_workflow_type"`
	LatestFailedWorkflowErrorCode string `json:"latest_failed_workflow_error_code"`
	LatestFailedWorkflowUpdatedAt string `json:"latest_failed_workflow_updated_at"`
	UpdatedAt                     string `json:"updated_at"`
}

type Reader interface {
	GetProjectOverview(context.Context, GetProjectOverviewInput) (Overview, error)
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "PROJECT_OVERVIEW_FAILED"
}

type DisabledReader struct{}

func NewDisabledReader() *DisabledReader {
	return &DisabledReader{}
}

func (r *DisabledReader) GetProjectOverview(context.Context, GetProjectOverviewInput) (Overview, error) {
	return Overview{}, &AppError{
		Code:    "PROJECT_OVERVIEW_BACKEND_UNCONFIGURED",
		Message: "project overview reader is not configured",
	}
}

type SQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type SQLQueryer interface {
	QueryContext(context.Context, string, ...any) (SQLRows, error)
}

type SQLTenantQueryer interface {
	QueryTenantContext(context.Context, string, string, ...any) (SQLRows, error)
}

type SQLDBQueryer struct {
	db *sql.DB
}

func NewSQLDBQueryer(db *sql.DB) *SQLDBQueryer {
	return &SQLDBQueryer{db: db}
}

func (q *SQLDBQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (q *SQLDBQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	tx, err := q.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULL::uuid, false)", strings.TrimSpace(tenantID)); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, query, args...)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return &tenantScopedRows{rows: rows, tx: tx}, nil
}

type tenantScopedRows struct {
	rows SQLRows
	tx   *sql.Tx
}

func (r *tenantScopedRows) Next() bool {
	return r.rows.Next()
}

func (r *tenantScopedRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *tenantScopedRows) Close() error {
	closeErr := r.rows.Close()
	rowsErr := r.rows.Err()
	if closeErr != nil || rowsErr != nil {
		_ = r.tx.Rollback()
		if closeErr != nil {
			return closeErr
		}
		return rowsErr
	}
	return r.tx.Commit()
}

func (r *tenantScopedRows) Err() error {
	return r.rows.Err()
}

type SQLReaderConfig struct {
	Queryer SQLQueryer
}

type SQLReader struct {
	queryer SQLQueryer
}

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	return &SQLReader{queryer: config.Queryer}
}

func (r *SQLReader) GetProjectOverview(ctx context.Context, input GetProjectOverviewInput) (Overview, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return Overview{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if r.queryer == nil {
		return Overview{}, &AppError{Code: "PROJECT_OVERVIEW_BACKEND_UNCONFIGURED", Message: "project overview reader is not configured"}
	}
	query := `WITH
source_counts AS (
  SELECT COUNT(*)::int AS source_file_count
  FROM source_files
  WHERE tenant_id::text = $1
    AND project_id::text = $2
),
seed_counts AS (
  SELECT COUNT(*)::int AS seed_run_count
  FROM workflow_runs
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND workflow_type = 'seed_pipeline'
),
latest_readiness AS (
  SELECT
    project_readiness_snapshot_id::text AS readiness_snapshot_id,
    run_id::text AS readiness_run_id,
    ready_asset_count,
    ready_entity_count,
    ready_relationship_count,
    ready_world_rule_count,
    COALESCE((metadata_jsonb->>'total_segment_count')::int, 0) AS total_segment_count,
    COALESCE((metadata_jsonb->>'succeeded_segment_count')::int, 0) AS succeeded_segment_count,
    COALESCE(metadata_jsonb->'failed_segment_ids', '[]'::jsonb)::text AS failed_segment_ids,
    updated_at::text AS readiness_updated_at
  FROM project_readiness_snapshots
  WHERE tenant_id::text = $1
    AND project_id::text = $2
  ORDER BY updated_at DESC
  LIMIT 1
),
asset_counts AS (
  SELECT
    COUNT(*)::int AS asset_count,
    MAX(updated_at)::text AS asset_updated_at
  FROM assets
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND enabled = true
),
latest_graph AS (
  SELECT
    node_count::int AS graph_node_count,
    edge_count::int AS graph_edge_count,
    updated_at::text AS graph_updated_at
  FROM story_graph_snapshots
  WHERE tenant_id::text = $1
    AND project_id::text = $2
  ORDER BY updated_at DESC
  LIMIT 1
),
worldline_session_counts AS (
  SELECT
    COUNT(*)::int AS worldline_session_count,
    MAX(updated_at)::text AS worldline_session_updated_at
  FROM worldline_sessions
  WHERE tenant_id::text = $1
    AND project_id::text = $2
),
worldline_event_counts AS (
  SELECT
    COUNT(*)::int AS worldline_event_count,
    MAX(updated_at)::text AS worldline_event_updated_at
  FROM worldline_events
  WHERE tenant_id::text = $1
    AND project_id::text = $2
),
character_counts AS (
  SELECT
    COUNT(*)::int AS character_interaction_count,
    MAX(updated_at)::text AS character_interaction_updated_at
  FROM character_interaction_sessions
  WHERE tenant_id::text = $1
    AND project_id::text = $2
),
writer_counts AS (
  SELECT
    COUNT(*)::int AS writer_run_count,
    MAX(updated_at)::text AS writer_run_updated_at
  FROM writer_runs
  WHERE tenant_id::text = $1
    AND project_id::text = $2
),
llm_activity_counts AS (
  SELECT
    COUNT(*)::int AS llm_activity_count,
    MAX(created_at)::text AS llm_activity_updated_at
  FROM llm_activity
  WHERE tenant_id::text = $1
    AND project_id::text = $2
),
llm_token_counts AS (
  SELECT
    COALESCE(SUM(quantity), 0)::int AS llm_token_count,
    MAX(created_at)::text AS llm_usage_updated_at
  FROM usage_events
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND usage_type = 'llm_tokens'
),
llm_enabled_channel_counts AS (
  SELECT
    COUNT(*)::int AS llm_enabled_channel_count,
    MAX(updated_at)::text AS llm_channel_updated_at
  FROM llm_channels
  WHERE (tenant_id::text = $1 OR tenant_id IS NULL)
    AND enabled = TRUE
),
valid_llm_bindings AS (
  SELECT
    b.module_key,
    MAX(b.updated_at)::text AS binding_updated_at
  FROM llm_module_bindings b
  JOIN llm_channels c
    ON c.channel_id = b.channel_id
   AND c.enabled = TRUE
   AND (c.tenant_id = b.tenant_id OR c.tenant_id IS NULL)
  JOIN llm_models m
    ON m.channel_id = b.channel_id
   AND m.model_id = b.model_id
   AND (m.tenant_id = b.tenant_id OR m.tenant_id IS NULL)
  WHERE b.tenant_id::text = $1
    AND (b.project_id::text = $2 OR b.project_id IS NULL)
  GROUP BY b.module_key
),
llm_bound_module_counts AS (
  SELECT
    COUNT(*)::int AS llm_bound_module_count,
    MAX(binding_updated_at)::text AS llm_binding_updated_at
  FROM valid_llm_bindings
),
required_llm_modules(module_key) AS (
  VALUES
    ('analysis_planner'),
    ('analysis_worker'),
    ('writer_orchestrator'),
    ('writer_composer'),
    ('writer_reviewer'),
    ('asset_ingestion'),
    ('worldline_director')
),
llm_missing_core_module_counts AS (
  SELECT
    (COUNT(*) FILTER (WHERE valid_llm_bindings.module_key IS NULL))::int AS llm_missing_core_module_count
  FROM required_llm_modules
  LEFT JOIN valid_llm_bindings
    ON valid_llm_bindings.module_key = required_llm_modules.module_key
),
llm_model_sync_health AS (
  SELECT
    (COUNT(*) FILTER (WHERE last_sync_status LIKE 'ok:%'))::int AS llm_sync_ok_channel_count,
    (COUNT(*) FILTER (WHERE COALESCE(last_sync_status, '') <> '' AND last_sync_status NOT LIKE 'ok:%'))::int AS llm_sync_failed_channel_count,
    (COUNT(*) FILTER (WHERE COALESCE(last_sync_status, '') = ''))::int AS llm_sync_pending_channel_count,
    COALESCE(MAX(last_sync_at)::text, '') AS llm_latest_sync_at
  FROM llm_channels
  WHERE (tenant_id::text = $1 OR tenant_id IS NULL)
    AND enabled = TRUE
),
llm_quota_policy_counts AS (
  SELECT EXISTS (
    SELECT 1
    FROM llm_quota_policies
    WHERE tenant_id::text = $1
      AND enabled = TRUE
      AND (
        scope_type = 'tenant'
        OR (scope_type = 'project' AND project_id::text = $2)
      )
  ) AS llm_has_quota_policy
),
active_workflow AS (
  SELECT
    run_id::text AS active_workflow_run_id,
    workflow_type AS active_workflow_type,
    status AS active_workflow_status,
    updated_at::text AS active_workflow_updated_at
  FROM workflow_runs
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND status IN ('queued', 'pending', 'running', 'in_progress')
  ORDER BY updated_at DESC
  LIMIT 1
),
latest_workflow AS (
  SELECT status AS latest_workflow_status, updated_at::text AS latest_workflow_updated_at
  FROM workflow_runs
  WHERE tenant_id::text = $1
    AND project_id::text = $2
  ORDER BY updated_at DESC
  LIMIT 1
),
latest_failed_workflow AS (
  SELECT
    run_id::text AS latest_failed_workflow_run_id,
    workflow_type AS latest_failed_workflow_type,
    COALESCE(error_code, '') AS latest_failed_workflow_error_code,
    updated_at::text AS latest_failed_workflow_updated_at
  FROM workflow_runs
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND status = 'failed'
  ORDER BY updated_at DESC
  LIMIT 1
)
SELECT
  $2::text AS project_id,
  CASE
    WHEN active_workflow.active_workflow_run_id IS NOT NULL THEN 'analyzing'
    WHEN COALESCE(latest_readiness.ready_asset_count, 0)
       + COALESCE(latest_readiness.ready_entity_count, 0)
       + COALESCE(latest_readiness.ready_relationship_count, 0)
       + COALESCE(latest_readiness.ready_world_rule_count, 0) > 0 THEN 'ready'
    WHEN latest_workflow.latest_workflow_status = 'failed' THEN 'blocked'
    WHEN COALESCE(asset_counts.asset_count, 0)
       + COALESCE(latest_graph.graph_node_count, 0)
       + COALESCE(latest_graph.graph_edge_count, 0)
       + COALESCE(worldline_session_counts.worldline_session_count, 0)
       + COALESCE(worldline_event_counts.worldline_event_count, 0)
       + COALESCE(character_counts.character_interaction_count, 0)
       + COALESCE(writer_counts.writer_run_count, 0)
       + COALESCE(llm_activity_counts.llm_activity_count, 0) > 0 THEN 'ready'
    WHEN source_counts.source_file_count > 0 OR seed_counts.seed_run_count > 0 THEN 'analyzing'
    ELSE 'empty'
  END AS status,
  source_counts.source_file_count,
  seed_counts.seed_run_count,
  COALESCE(active_workflow.active_workflow_run_id, '') AS active_workflow_run_id,
  COALESCE(active_workflow.active_workflow_type, '') AS active_workflow_type,
  COALESCE(active_workflow.active_workflow_status, '') AS active_workflow_status,
  COALESCE(latest_readiness.readiness_snapshot_id, '') AS readiness_snapshot_id,
  COALESCE(latest_readiness.readiness_run_id, '') AS readiness_run_id,
  COALESCE(latest_readiness.ready_asset_count, 0)::int AS ready_asset_count,
  COALESCE(latest_readiness.ready_entity_count, 0)::int AS ready_entity_count,
  COALESCE(latest_readiness.ready_relationship_count, 0)::int AS ready_relationship_count,
  COALESCE(latest_readiness.ready_world_rule_count, 0)::int AS ready_world_rule_count,
  COALESCE(latest_readiness.total_segment_count, 0)::int AS total_segment_count,
  COALESCE(latest_readiness.succeeded_segment_count, 0)::int AS succeeded_segment_count,
  COALESCE(latest_readiness.failed_segment_ids, '[]') AS failed_segment_ids,
  COALESCE(asset_counts.asset_count, 0)::int AS asset_count,
  COALESCE(latest_graph.graph_node_count, 0)::int AS graph_node_count,
  COALESCE(latest_graph.graph_edge_count, 0)::int AS graph_edge_count,
  COALESCE(worldline_session_counts.worldline_session_count, 0)::int AS worldline_session_count,
  COALESCE(worldline_event_counts.worldline_event_count, 0)::int AS worldline_event_count,
  COALESCE(character_counts.character_interaction_count, 0)::int AS character_interaction_count,
  COALESCE(writer_counts.writer_run_count, 0)::int AS writer_run_count,
  COALESCE(llm_activity_counts.llm_activity_count, 0)::int AS llm_activity_count,
  COALESCE(llm_token_counts.llm_token_count, 0)::int AS llm_token_count,
  COALESCE(llm_enabled_channel_counts.llm_enabled_channel_count, 0)::int AS llm_enabled_channel_count,
  COALESCE(llm_bound_module_counts.llm_bound_module_count, 0)::int AS llm_bound_module_count,
  COALESCE(llm_missing_core_module_counts.llm_missing_core_module_count, 0)::int AS llm_missing_core_module_count,
  COALESCE(llm_model_sync_health.llm_sync_ok_channel_count, 0)::int AS llm_sync_ok_channel_count,
  COALESCE(llm_model_sync_health.llm_sync_failed_channel_count, 0)::int AS llm_sync_failed_channel_count,
  COALESCE(llm_model_sync_health.llm_sync_pending_channel_count, 0)::int AS llm_sync_pending_channel_count,
  COALESCE(llm_model_sync_health.llm_latest_sync_at, '') AS llm_latest_sync_at,
  COALESCE(llm_quota_policy_counts.llm_has_quota_policy, false) AS llm_has_quota_policy,
  COALESCE(latest_failed_workflow.latest_failed_workflow_run_id, '') AS latest_failed_workflow_run_id,
  COALESCE(latest_failed_workflow.latest_failed_workflow_type, '') AS latest_failed_workflow_type,
  COALESCE(latest_failed_workflow.latest_failed_workflow_error_code, '') AS latest_failed_workflow_error_code,
  COALESCE(latest_failed_workflow.latest_failed_workflow_updated_at, '') AS latest_failed_workflow_updated_at,
  COALESCE(
    latest_readiness.readiness_updated_at,
    active_workflow.active_workflow_updated_at,
    latest_workflow.latest_workflow_updated_at,
    asset_counts.asset_updated_at,
    latest_graph.graph_updated_at,
    worldline_session_counts.worldline_session_updated_at,
    worldline_event_counts.worldline_event_updated_at,
    character_counts.character_interaction_updated_at,
    writer_counts.writer_run_updated_at,
    llm_activity_counts.llm_activity_updated_at,
    llm_token_counts.llm_usage_updated_at,
    llm_enabled_channel_counts.llm_channel_updated_at,
    llm_bound_module_counts.llm_binding_updated_at,
    llm_model_sync_health.llm_latest_sync_at,
    latest_failed_workflow.latest_failed_workflow_updated_at,
    ''
  ) AS updated_at
FROM source_counts
CROSS JOIN seed_counts
LEFT JOIN latest_readiness ON true
LEFT JOIN asset_counts ON true
LEFT JOIN latest_graph ON true
LEFT JOIN worldline_session_counts ON true
LEFT JOIN worldline_event_counts ON true
LEFT JOIN character_counts ON true
LEFT JOIN writer_counts ON true
LEFT JOIN llm_activity_counts ON true
LEFT JOIN llm_token_counts ON true
LEFT JOIN llm_enabled_channel_counts ON true
LEFT JOIN llm_bound_module_counts ON true
LEFT JOIN llm_missing_core_module_counts ON true
LEFT JOIN llm_model_sync_health ON true
LEFT JOIN llm_quota_policy_counts ON true
LEFT JOIN active_workflow ON true
LEFT JOIN latest_workflow ON true
LEFT JOIN latest_failed_workflow ON true`
	rows, err := r.queryRows(ctx, tenantID, query, tenantID, projectID)
	if err != nil {
		return Overview{}, queryFailed()
	}

	overview, err := scanOverview(rows)
	if err != nil {
		_ = rows.Close()
		return Overview{}, err
	}
	if err := rows.Close(); err != nil {
		return Overview{}, queryFailed()
	}
	return overview, nil
}

func (r *SQLReader) queryRows(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := r.queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return r.queryer.QueryContext(ctx, query, args...)
}

func scanOverview(rows SQLRows) (Overview, error) {
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return Overview{}, queryFailed()
		}
		return Overview{}, &AppError{Code: "NOT_FOUND", Message: "project overview not found"}
	}
	var overview Overview
	var failedSegmentIDsRaw string
	if err := rows.Scan(
		&overview.ProjectID,
		&overview.Status,
		&overview.SourceFileCount,
		&overview.SeedRunCount,
		&overview.ActiveWorkflowRunID,
		&overview.ActiveWorkflowType,
		&overview.ActiveWorkflowStatus,
		&overview.ReadinessSnapshotID,
		&overview.ReadinessRunID,
		&overview.ReadyAssetCount,
		&overview.ReadyEntityCount,
		&overview.ReadyRelationshipCount,
		&overview.ReadyWorldRuleCount,
		&overview.TotalSegmentCount,
		&overview.SucceededSegmentCount,
		&failedSegmentIDsRaw,
		&overview.AssetCount,
		&overview.GraphNodeCount,
		&overview.GraphEdgeCount,
		&overview.WorldlineSessionCount,
		&overview.WorldlineEventCount,
		&overview.CharacterInteractionCount,
		&overview.WriterRunCount,
		&overview.LLMActivityCount,
		&overview.LLMTokenCount,
		&overview.LLMEnabledChannelCount,
		&overview.LLMBoundModuleCount,
		&overview.LLMMissingCoreModuleCount,
		&overview.LLMSyncOKChannelCount,
		&overview.LLMSyncFailedChannelCount,
		&overview.LLMSyncPendingChannelCount,
		&overview.LLMLatestSyncAt,
		&overview.LLMHasQuotaPolicy,
		&overview.LatestFailedWorkflowRunID,
		&overview.LatestFailedWorkflowType,
		&overview.LatestFailedWorkflowErrorCode,
		&overview.LatestFailedWorkflowUpdatedAt,
		&overview.UpdatedAt,
	); err != nil {
		return Overview{}, queryFailed()
	}
	if err := rows.Err(); err != nil {
		return Overview{}, queryFailed()
	}
	overview.FailedSegmentIDs = parseFailedSegmentIDs(failedSegmentIDsRaw)
	return overview, nil
}

func parseFailedSegmentIDs(raw string) []string {
	ids := []string{}
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" || trimmed == "null" {
		return ids
	}
	if err := json.Unmarshal([]byte(trimmed), &ids); err != nil {
		return []string{}
	}
	return ids
}

func queryFailed() *AppError {
	return &AppError{Code: "PROJECT_OVERVIEW_QUERY_FAILED", Message: "project overview query failed"}
}
