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
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, and workflow_type are required"}
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
	_, err = s.execer.ExecContext(
		ctx,
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
		return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	return nil
}

func missingAssetReindexAdmissionContext(input AssetReindexAdmissionInput) bool {
	return strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == ""
}
