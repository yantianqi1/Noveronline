package workflows

import (
	"context"
	"encoding/json"
	"strings"
)

type SQLAssetReindexAdmissionStoreConfig struct {
	Execer WriterAdmissionSQLExecer
}

type SQLAssetReindexAdmissionStore struct {
	execer WriterAdmissionSQLExecer
}

func NewSQLAssetReindexAdmissionStore(config SQLAssetReindexAdmissionStoreConfig) *SQLAssetReindexAdmissionStore {
	return &SQLAssetReindexAdmissionStore{execer: config.Execer}
}

func (s *SQLAssetReindexAdmissionStore) AdmitAssetReindexRun(ctx context.Context, input AssetReindexAdmissionInput) error {
	if missingAssetReindexAdmissionContext(input) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, actor_user_id, and request_id are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "ASSET_REINDEX_BACKEND_UNCONFIGURED", Message: "asset reindex admission store is not configured"}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "queued"
	}
	eventPayload, err := json.Marshal(map[string]any{
		"status":        status,
		"workflow_type": strings.TrimSpace(input.WorkflowType),
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      strings.TrimSpace(input.TraceID),
		"scope":         strings.TrimSpace(input.Scope),
		"mode":          strings.TrimSpace(input.Mode),
		"module_key":    AssetReindexModuleKey,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "asset reindex admission payload must be JSON serializable"}
	}
	query := `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id,
    run_id,
    workflow_type,
    project_id,
    status,
    progress,
    message,
    started_by,
    temporal_workflow_id
  )
  VALUES (
    $1::uuid,
    $3::uuid,
    $4,
    $2::uuid,
    $5,
    0,
    $8,
    NULLIF($6, '')::uuid,
    $7
  )
  RETURNING run_id
)
INSERT INTO workflow_events (
  tenant_id,
  run_id,
  workflow_type,
  project_id,
  event_type,
  sequence,
  payload_jsonb
)
SELECT
  $1::uuid,
  workflow_insert.run_id,
  $4,
  $2::uuid,
  'workflow.queued',
  1,
  $9::jsonb
FROM workflow_insert`
	result, err := execAdmissionSQL(
		ctx,
		s.execer,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ActorUserID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.WorkflowType),
		status,
		strings.TrimSpace(input.ActorUserID),
		strings.TrimSpace(input.TemporalWorkflowID),
		"queued",
		string(eventPayload),
	)
	if err != nil {
		return assetReindexAdmissionFailed()
	}
	if !assetReindexWriteAffectedOneRow(result) {
		return assetReindexAdmissionFailed()
	}
	return nil
}

func (s *SQLAssetReindexAdmissionStore) RecordAssetReindexStartFailure(ctx context.Context, input AssetReindexAdmissionInput) error {
	if missingAssetReindexAdmissionContext(input) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, actor_user_id, and request_id are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "ASSET_REINDEX_BACKEND_UNCONFIGURED", Message: "asset reindex admission store is not configured"}
	}
	payload, err := json.Marshal(map[string]any{
		"status":        "failed",
		"workflow_type": strings.TrimSpace(input.WorkflowType),
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      strings.TrimSpace(input.TraceID),
		"scope":         strings.TrimSpace(input.Scope),
		"mode":          strings.TrimSpace(input.Mode),
		"module_key":    AssetReindexModuleKey,
		"error_code":    "WORKFLOW_START_FAILED",
		"error_message": assetReindexStartFailedMessage,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "asset reindex start failure payload must be JSON serializable"}
	}
	query := `WITH workflow_update AS (
  UPDATE workflow_runs
  SET
    status = 'failed',
    progress = 0,
    message = $5,
    error_code = 'WORKFLOW_START_FAILED',
    error_message = $5,
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND run_id = $3::uuid
    AND workflow_type = $4
    AND status = 'queued'
  RETURNING tenant_id, run_id, workflow_type, project_id
),
next_sequence AS (
  SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
  FROM workflow_events
  WHERE tenant_id = $1::uuid
    AND run_id = $3::uuid
)
INSERT INTO workflow_events (
  tenant_id,
  run_id,
  workflow_type,
  project_id,
  event_type,
  sequence,
  payload_jsonb
)
SELECT
  workflow_update.tenant_id,
  workflow_update.run_id,
  workflow_update.workflow_type,
  workflow_update.project_id,
  'workflow.start_failed',
  next_sequence.sequence,
  $6::jsonb
FROM workflow_update
CROSS JOIN next_sequence`
	result, err := execAdmissionSQL(
		ctx,
		s.execer,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ActorUserID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.WorkflowType),
		assetReindexStartFailedMessage,
		string(payload),
	)
	if err != nil {
		return assetReindexStartFailureRecordFailed()
	}
	if !assetReindexWriteAffectedOneRow(result) {
		return assetReindexStartFailureRecordFailed()
	}
	return nil
}

func missingAssetReindexAdmissionContext(input AssetReindexAdmissionInput) bool {
	return strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == "" ||
		strings.TrimSpace(input.ActorUserID) == "" ||
		strings.TrimSpace(input.RequestID) == ""
}

func assetReindexWriteAffectedOneRow(result interface{ RowsAffected() (int64, error) }) bool {
	if result == nil {
		return false
	}
	rowsAffected, err := result.RowsAffected()
	return err == nil && rowsAffected == 1
}

func assetReindexAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "asset reindex admission failed"}
}

func assetReindexStartFailureRecordFailed() *AppError {
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to record asset_reindex workflow start failure"}
}
