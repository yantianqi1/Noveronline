package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
)

type WriterAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	TraceID            string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	Mode               string
	Status             string
	ModuleKey          string
	Instruction        string
	Options            map[string]any
}

type WriterCancellationInput struct {
	TenantID    string
	RunID       string
	ActorUserID string
	RequestID   string
	Status      string
}

type WriterAdmissionSQLExecer interface {
	ExecContext(context.Context, string, ...any) (sql.Result, error)
}

type WriterAdmissionSQLTenantExecer interface {
	ExecTenantContext(context.Context, string, string, string, ...any) (sql.Result, error)
}

type SQLWriterAdmissionStoreConfig struct {
	Execer WriterAdmissionSQLExecer
}

type SQLWriterAdmissionStore struct {
	execer WriterAdmissionSQLExecer
}

type sqlDBWriterAdmissionExecer struct {
	db *sql.DB
}

func NewSQLDBWriterAdmissionExecer(db *sql.DB) WriterAdmissionSQLExecer {
	return sqlDBWriterAdmissionExecer{db: db}
}

func (e sqlDBWriterAdmissionExecer) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	return e.db.ExecContext(ctx, query, args...)
}

func (e sqlDBWriterAdmissionExecer) ExecTenantContext(ctx context.Context, tenantID string, projectID string, query string, args ...any) (sql.Result, error) {
	tx, err := e.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)", strings.TrimSpace(tenantID), strings.TrimSpace(projectID)); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	result, err := tx.ExecContext(ctx, query, args...)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, err
	}
	return result, nil
}

func execAdmissionSQL(ctx context.Context, execer WriterAdmissionSQLExecer, tenantID string, projectID string, query string, args ...any) (sql.Result, error) {
	if tenantExecer, ok := execer.(WriterAdmissionSQLTenantExecer); ok {
		return tenantExecer.ExecTenantContext(ctx, tenantID, projectID, query, args...)
	}
	return execer.ExecContext(ctx, query, args...)
}

func NewSQLWriterAdmissionStore(config SQLWriterAdmissionStoreConfig) *SQLWriterAdmissionStore {
	return &SQLWriterAdmissionStore{execer: config.Execer}
}

func (s *SQLWriterAdmissionStore) AdmitWriterRun(ctx context.Context, input WriterAdmissionInput) error {
	if missingAdmissionContext(input) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, mode, module_key, and instruction are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer admission store is not configured"}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "queued"
	}
	optionsJSON, err := json.Marshal(sanitizeWriterAdmissionValue(input.Options))
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "writer run options must be JSON serializable"}
	}
	eventPayload, err := json.Marshal(map[string]any{
		"status":        status,
		"workflow_type": strings.TrimSpace(input.WorkflowType),
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      strings.TrimSpace(input.TraceID),
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "writer run admission payload must be JSON serializable"}
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
),
writer_insert AS (
  INSERT INTO writer_runs (
    tenant_id,
    run_id,
    workflow_run_id,
    project_id,
    mode,
    status,
    module_key,
    instruction,
    options_jsonb,
    created_by
  )
  SELECT
    $1::uuid,
    $3::uuid,
    workflow_insert.run_id,
    $2::uuid,
    $9,
    $5,
    $10,
    $11,
    $12::jsonb,
    NULLIF($6, '')::uuid
  FROM workflow_insert
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
  writer_insert.run_id,
  $4,
  $2::uuid,
  'workflow.queued',
  1,
  $13::jsonb
FROM writer_insert`
	_, err = execAdmissionSQL(
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
		strings.TrimSpace(input.Mode),
		strings.TrimSpace(input.ModuleKey),
		strings.TrimSpace(input.Instruction),
		string(optionsJSON),
		string(eventPayload),
	)
	if err != nil {
		return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: err.Error()}
	}
	return nil
}

func (s *SQLWriterAdmissionStore) CancelWriterRun(ctx context.Context, input WriterCancellationInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer cancellation store is not configured"}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "cancelled"
	}
	payload, err := json.Marshal(map[string]any{
		"status":        status,
		"request_id":    strings.TrimSpace(input.RequestID),
		"actor_user_id": strings.TrimSpace(input.ActorUserID),
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "writer cancellation payload must be JSON serializable"}
	}
	query := `WITH writer_update AS (
  UPDATE writer_runs
  SET
    status = $3,
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND run_id = $2::uuid
  RETURNING run_id, project_id
),
workflow_update AS (
  UPDATE workflow_runs
  SET
    status = $3,
    message = $4,
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND run_id = $2::uuid
  RETURNING run_id
),
next_sequence AS (
  SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
  FROM workflow_events
  WHERE tenant_id = $1::uuid
    AND run_id = $2::uuid
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
  writer_update.run_id,
  $5,
  writer_update.project_id,
  'writer.run.cancelled',
  next_sequence.sequence,
  $6::jsonb
FROM writer_update
JOIN workflow_update ON workflow_update.run_id = writer_update.run_id
CROSS JOIN next_sequence`
	result, err := execAdmissionSQL(
		ctx,
		s.execer,
		strings.TrimSpace(input.TenantID),
		"",
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
		status,
		"cancelled",
		WriterWorkflowType,
		string(payload),
	)
	if err != nil {
		return &AppError{Code: "WORKFLOW_CANCEL_FAILED", Message: err.Error()}
	}
	rowsAffected, err := result.RowsAffected()
	if err == nil && rowsAffected != 1 {
		return &AppError{Code: "WORKFLOW_RUN_NOT_FOUND", Message: "writer run admission rows not found for cancellation"}
	}
	return nil
}

func missingAdmissionContext(input WriterAdmissionInput) bool {
	return strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == "" ||
		strings.TrimSpace(input.Mode) == "" ||
		strings.TrimSpace(input.ModuleKey) == "" ||
		strings.TrimSpace(input.Instruction) == ""
}

func moduleKeyFromWriterOptions(options map[string]any) string {
	if moduleKey, ok := options["module_key"].(string); ok && strings.TrimSpace(moduleKey) != "" {
		return strings.TrimSpace(moduleKey)
	}
	return "writer_composer"
}

func sanitizeWriterAdmissionValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		cleaned := map[string]any{}
		for key, nested := range typed {
			if isHighRiskWriterAdmissionKey(key) {
				continue
			}
			cleaned[key] = sanitizeWriterAdmissionValue(nested)
		}
		return cleaned
	case []any:
		cleaned := make([]any, 0, len(typed))
		for _, nested := range typed {
			cleaned = append(cleaned, sanitizeWriterAdmissionValue(nested))
		}
		return cleaned
	default:
		return value
	}
}

func isHighRiskWriterAdmissionKey(key string) bool {
	normalized := strings.ToLower(strings.TrimSpace(key))
	switch normalized {
	case "api_key", "apikey", "encrypted_api_key", "encryptedapikey",
		"credential_ref", "credentialref", "credential", "credentials",
		"prompt", "response", "body", "content", "draft", "manuscript",
		"body_text", "content_text", "source_text", "source_material", "material_text",
		"raw_text", "raw_body", "raw_content", "candidate_body", "candidate_event_body", "event_body":
		return true
	default:
		return false
	}
}
