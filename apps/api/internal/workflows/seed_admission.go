package workflows

import (
	"context"
	"encoding/json"
	"strings"
)

type SQLSeedAdmissionStoreConfig struct {
	Execer WriterAdmissionSQLExecer
}

type SQLSeedAdmissionStore struct {
	execer WriterAdmissionSQLExecer
}

func NewSQLSeedAdmissionStore(config SQLSeedAdmissionStoreConfig) *SQLSeedAdmissionStore {
	return &SQLSeedAdmissionStore{execer: config.Execer}
}

func (s *SQLSeedAdmissionStore) AdmitSeedRun(ctx context.Context, input SeedAdmissionInput) error {
	if missingSeedAdmissionContext(input) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, and upload_id are required"}
	}
	if invalidSeedAdmissionUUIDContext(input) {
		return invalidSeedAdmissionContext()
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "seed admission store is not configured"}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "queued"
	}
	eventPayloadMap := map[string]any{
		"status":        status,
		"workflow_type": strings.TrimSpace(input.WorkflowType),
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      strings.TrimSpace(input.TraceID),
		"upload_id":     strings.TrimSpace(input.UploadID),
	}
	eventPayload, err := json.Marshal(eventPayloadMap)
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "seed run admission payload must be JSON serializable"}
	}
	query := `WITH source_update AS (
  UPDATE source_files
  SET parse_status = 'parsing',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND upload_id = $10::uuid
    AND file_id = $11::uuid
    AND parse_status IN ('uploaded', 'parsed', 'failed', 'cancelled')
  RETURNING upload_id, file_id
),
workflow_insert AS (
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
  SELECT
    $1::uuid,
    $3::uuid,
    $4,
    $2::uuid,
    $5,
    0,
    $8,
    NULLIF($6, '')::uuid,
    $7
  FROM source_update
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
  $9::jsonb || jsonb_build_object('source_file_id', source_update.file_id::text)
FROM workflow_insert
CROSS JOIN source_update`
	result, err := execAdmissionSQL(
		ctx,
		s.execer,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
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
		strings.TrimSpace(input.UploadID),
		strings.TrimSpace(input.SourceFileID),
	)
	if err != nil {
		return workflowAdmissionFailed()
	}
	if result == nil {
		return workflowAdmissionFailed()
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return workflowAdmissionFailed()
	}
	if rowsAffected == 0 {
		return sourceFileNotUploadedForSeed()
	}
	return nil
}

func (s *SQLSeedAdmissionStore) RecordSeedRunStartFailure(ctx context.Context, input SeedStartFailureInput) error {
	if missingSeedStartFailureContext(input) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, and upload_id are required"}
	}
	if invalidSeedStartFailureUUIDContext(input) {
		return invalidSeedAdmissionContext()
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "seed admission store is not configured"}
	}
	errorCode := "WORKFLOW_FAILED"
	errorMessage := seedWorkflowStartFailedMessage
	payload, err := json.Marshal(map[string]any{
		"status":        "failed",
		"workflow_type": strings.TrimSpace(input.WorkflowType),
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      strings.TrimSpace(input.TraceID),
		"upload_id":     strings.TrimSpace(input.UploadID),
		"error_code":    errorCode,
		"error_message": errorMessage,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "seed workflow failure payload must be JSON serializable"}
	}
	query := `WITH workflow_update AS (
  UPDATE workflow_runs
  SET
    status = 'failed',
    message = $6,
    error_code = $7,
    error_message = $6,
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND run_id = $3::uuid
    AND workflow_type = $4
    AND status = 'queued'
  RETURNING run_id, project_id, workflow_type
),
source_update AS (
  UPDATE source_files
  SET
    parse_status = 'uploaded',
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND upload_id = $5::uuid
    AND file_id = $9::uuid
    AND parse_status = 'parsing'
  RETURNING upload_id, file_id
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
  $1::uuid,
  workflow_update.run_id,
  workflow_update.workflow_type,
  workflow_update.project_id,
  'workflow.failed',
  next_sequence.sequence,
  CASE
    WHEN source_update.file_id IS NULL THEN $8::jsonb
    ELSE $8::jsonb || jsonb_build_object('source_file_id', source_update.file_id::text)
  END
FROM workflow_update
CROSS JOIN next_sequence
LEFT JOIN source_update ON TRUE`
	result, err := execAdmissionSQL(
		ctx,
		s.execer,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.WorkflowType),
		strings.TrimSpace(input.UploadID),
		errorMessage,
		errorCode,
		string(payload),
		strings.TrimSpace(input.SourceFileID),
	)
	if err != nil {
		return workflowStartFailureRecordFailed()
	}
	if result == nil {
		return workflowStartFailureRecordFailed()
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return workflowStartFailureRecordFailed()
	}
	if rowsAffected == 0 {
		return workflowStartFailureRecordFailed()
	}
	return nil
}

func missingSeedAdmissionContext(input SeedAdmissionInput) bool {
	return strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == "" ||
		strings.TrimSpace(input.UploadID) == "" ||
		strings.TrimSpace(input.SourceFileID) == ""
}

func missingSeedStartFailureContext(input SeedStartFailureInput) bool {
	return strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == "" ||
		strings.TrimSpace(input.UploadID) == "" ||
		strings.TrimSpace(input.SourceFileID) == ""
}

func invalidSeedAdmissionUUIDContext(input SeedAdmissionInput) bool {
	return !isSeedUUID(input.TenantID) ||
		!isSeedUUID(input.ProjectID) ||
		!isSeedUUID(input.RunID) ||
		!isOptionalSeedUUID(input.ActorUserID) ||
		!isSeedUUID(input.UploadID) ||
		!isSeedUUID(input.SourceFileID)
}

func invalidSeedStartFailureUUIDContext(input SeedStartFailureInput) bool {
	return !isSeedUUID(input.TenantID) ||
		!isSeedUUID(input.ProjectID) ||
		!isSeedUUID(input.RunID) ||
		!isSeedUUID(input.UploadID) ||
		!isSeedUUID(input.SourceFileID)
}

func isOptionalSeedUUID(value string) bool {
	value = strings.TrimSpace(value)
	return value == "" || isSeedUUID(value)
}

func isSeedUUID(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 36 {
		return false
	}
	for index, char := range value {
		switch index {
		case 8, 13, 18, 23:
			if char != '-' {
				return false
			}
		default:
			if !isSeedHexChar(char) {
				return false
			}
		}
	}
	return true
}

func isSeedHexChar(char rune) bool {
	return (char >= '0' && char <= '9') ||
		(char >= 'a' && char <= 'f') ||
		(char >= 'A' && char <= 'F')
}

func invalidSeedAdmissionContext() *AppError {
	return &AppError{Code: "VALIDATION_FAILED", Message: "seed admission context is invalid"}
}

func workflowAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "workflow admission failed"}
}

func workflowStartFailureRecordFailed() *AppError {
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to record seed workflow start failure"}
}

func sourceFileNotUploadedForSeed() *AppError {
	return &AppError{Code: "SOURCE_FILE_NOT_UPLOADED", Message: "source file upload must be completed before seed run"}
}
