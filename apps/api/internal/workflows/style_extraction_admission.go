package workflows

import (
	"context"
	"encoding/json"
	"strings"
)

type SQLStyleExtractionAdmissionStoreConfig struct {
	Execer WriterAdmissionSQLExecer
}

type SQLStyleExtractionAdmissionStore struct {
	execer WriterAdmissionSQLExecer
}

func NewSQLStyleExtractionAdmissionStore(config SQLStyleExtractionAdmissionStoreConfig) *SQLStyleExtractionAdmissionStore {
	return &SQLStyleExtractionAdmissionStore{execer: config.Execer}
}

func (s *SQLStyleExtractionAdmissionStore) AdmitStyleExtractionRun(ctx context.Context, input StyleExtractionAdmissionInput) error {
	if missingStyleExtractionAdmissionContext(input) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, and workflow_type are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "STYLE_EXTRACTION_BACKEND_UNCONFIGURED", Message: "style extraction admission store is not configured"}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "queued"
	}
	eventPayload, err := json.Marshal(map[string]any{
		"status":          status,
		"workflow_type":   strings.TrimSpace(input.WorkflowType),
		"request_id":      strings.TrimSpace(input.RequestID),
		"trace_id":        strings.TrimSpace(input.TraceID),
		"source_asset_id": strings.TrimSpace(input.SourceAssetID),
		"scope":           strings.TrimSpace(input.Scope),
		"module_key":      StyleExtractionModuleKey,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "style extraction admission payload must be JSON serializable"}
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

func missingStyleExtractionAdmissionContext(input StyleExtractionAdmissionInput) bool {
	return strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == ""
}
