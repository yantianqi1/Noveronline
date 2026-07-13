package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
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
	ChapterID          string
	SceneID            string
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

// WriterAdmissionSQLQueryer supports request_id replay lookups. When the execer is a
// plain Execer without Query support, AdmitWriterRun falls back to insert-only behavior.
type WriterAdmissionSQLQueryer interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
}

type WriterAdmissionSQLTenantQueryer interface {
	QueryRowTenantContext(context.Context, string, string, string, ...any) *sql.Row
}

type SQLWriterAdmissionStoreConfig struct {
	Execer WriterAdmissionSQLExecer
	// DB enables request_id replay and compensation with proper tenant transactions.
	// When set, it is preferred over Execer for Admit/Compensate.
	DB *sql.DB
}

type SQLWriterAdmissionStore struct {
	execer WriterAdmissionSQLExecer
	db     *sql.DB
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
	return &SQLWriterAdmissionStore{execer: config.Execer, db: config.DB}
}

func (s *SQLWriterAdmissionStore) AdmitWriterRun(ctx context.Context, input WriterAdmissionInput) (WriterRun, bool, error) {
	if missingAdmissionContext(input) {
		return WriterRun{}, false, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, mode, module_key, and instruction are required"}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "queued"
	}
	proposed := WriterRun{
		RunID:       strings.TrimSpace(input.RunID),
		TraceID:     strings.TrimSpace(input.TraceID),
		TenantID:    strings.TrimSpace(input.TenantID),
		ProjectID:   strings.TrimSpace(input.ProjectID),
		Mode:        strings.TrimSpace(input.Mode),
		Instruction: strings.TrimSpace(input.Instruction),
		Status:      status,
	}
	if proposed.TraceID == "" {
		proposed.TraceID = traceIDForRun(proposed.RunID)
	}

	// Preferred path: full DB transaction with request_id replay.
	if s.db != nil {
		return s.admitWriterRunWithDB(ctx, input, proposed)
	}
	if s.execer == nil {
		return WriterRun{}, false, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer admission store is not configured"}
	}
	if err := s.insertWriterAdmission(ctx, input, proposed); err != nil {
		return WriterRun{}, false, err
	}
	return proposed, false, nil
}

func (s *SQLWriterAdmissionStore) admitWriterRunWithDB(ctx context.Context, input WriterAdmissionInput, proposed WriterRun) (WriterRun, bool, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return WriterRun{}, false, writerAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
		proposed.TenantID, proposed.ProjectID); err != nil {
		return WriterRun{}, false, writerAdmissionFailed()
	}
	if existing, found, replayErr := findWriterRunReplay(ctx, tx, input); replayErr != nil {
		return WriterRun{}, false, replayErr
	} else if found {
		if err := tx.Commit(); err != nil {
			return WriterRun{}, false, writerAdmissionFailed()
		}
		return existing, true, nil
	}
	if err := insertWriterAdmissionTx(ctx, tx, input, proposed); err != nil {
		return WriterRun{}, false, err
	}
	if err := tx.Commit(); err != nil {
		return WriterRun{}, false, writerAdmissionFailed()
	}
	return proposed, false, nil
}

func findWriterRunReplay(ctx context.Context, tx *sql.Tx, input WriterAdmissionInput) (WriterRun, bool, error) {
	requestID := strings.TrimSpace(input.RequestID)
	if requestID == "" {
		return WriterRun{}, false, nil
	}
	workflowType := strings.TrimSpace(input.WorkflowType)
	if workflowType == "" {
		workflowType = WriterWorkflowType
	}
	var run WriterRun
	var mode, instruction string
	err := tx.QueryRowContext(ctx, `
SELECT writer.run_id::text,
  COALESCE(queued.payload_jsonb->>'trace_id', ''),
  writer.project_id::text,
  writer.mode,
  writer.instruction,
  writer.status
FROM writer_runs AS writer
JOIN workflow_runs AS workflow
  ON workflow.tenant_id = writer.tenant_id
 AND workflow.run_id = writer.workflow_run_id
JOIN workflow_events AS queued
  ON queued.tenant_id = workflow.tenant_id
 AND queued.run_id = workflow.run_id
 AND queued.event_type = 'workflow.queued'
WHERE writer.tenant_id = $1::uuid
  AND writer.project_id = $2::uuid
  AND workflow.workflow_type = $3
  AND queued.payload_jsonb->>'request_id' = $4
ORDER BY queued.created_at ASC
LIMIT 1`,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		workflowType,
		requestID,
	).Scan(&run.RunID, &run.TraceID, &run.ProjectID, &mode, &instruction, &run.Status)
	if errors.Is(err, sql.ErrNoRows) {
		return WriterRun{}, false, nil
	}
	if err != nil {
		return WriterRun{}, false, writerAdmissionFailed()
	}
	// Same request_id must not be reused for a different writer request body.
	if mode != strings.TrimSpace(input.Mode) || instruction != strings.TrimSpace(input.Instruction) {
		return WriterRun{}, false, &AppError{
			Code:    "IDEMPOTENCY_CONFLICT",
			Message: "request_id was already used with a different writer run request",
		}
	}
	run.TenantID = strings.TrimSpace(input.TenantID)
	run.Mode = mode
	run.Instruction = instruction
	if strings.TrimSpace(run.TraceID) == "" {
		run.TraceID = traceIDForRun(run.RunID)
	}
	return run, true, nil
}

func (s *SQLWriterAdmissionStore) insertWriterAdmission(ctx context.Context, input WriterAdmissionInput, proposed WriterRun) error {
	return insertWriterAdmissionViaExecer(ctx, s.execer, input, proposed)
}

func insertWriterAdmissionViaExecer(ctx context.Context, execer WriterAdmissionSQLExecer, input WriterAdmissionInput, proposed WriterRun) error {
	status := proposed.Status
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
		"trace_id":      proposed.TraceID,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "writer run admission payload must be JSON serializable"}
	}
	query := writerAdmissionInsertSQL()
	_, err = execAdmissionSQL(
		ctx,
		execer,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		proposed.RunID,
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
		strings.TrimSpace(input.ChapterID),
		strings.TrimSpace(input.SceneID),
	)
	if err != nil {
		return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "writer run admission failed"}
	}
	return nil
}

func insertWriterAdmissionTx(ctx context.Context, tx *sql.Tx, input WriterAdmissionInput, proposed WriterRun) error {
	status := proposed.Status
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
		"trace_id":      proposed.TraceID,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "writer run admission payload must be JSON serializable"}
	}
	_, err = tx.ExecContext(ctx, writerAdmissionInsertSQL(),
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		proposed.RunID,
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
		strings.TrimSpace(input.ChapterID),
		strings.TrimSpace(input.SceneID),
	)
	if err != nil {
		return writerAdmissionFailed()
	}
	return nil
}

func writerAdmissionInsertSQL() string {
	return `WITH workflow_insert AS (
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
    chapter_id,
    scene_id,
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
    NULLIF($14, '')::uuid,
    NULLIF($15, '')::uuid,
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
}

func (s *SQLWriterAdmissionStore) CompensateWriterRunStart(ctx context.Context, input WriterCompensationInput) error {
	tenantID := strings.TrimSpace(input.TenantID)
	runID := strings.TrimSpace(input.RunID)
	if tenantID == "" || runID == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	payload, err := json.Marshal(map[string]any{
		"status":        "failed",
		"workflow_type": WriterWorkflowType,
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      strings.TrimSpace(input.TraceID),
		"error_code":    "WORKFLOW_START_FAILED",
		"message":       "writer workflow failed to start",
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "writer compensation payload must be JSON serializable"}
	}
	query := `WITH writer_update AS (
  UPDATE writer_runs
  SET
    status = 'failed',
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND run_id = $2::uuid
    AND status = 'queued'
  RETURNING run_id, project_id
),
workflow_update AS (
  UPDATE workflow_runs
  SET
    status = 'failed',
    progress = 0,
    message = 'writer workflow failed to start',
    error_code = 'WORKFLOW_START_FAILED',
    error_message = 'writer workflow failed to start',
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND run_id = $2::uuid
    AND status = 'queued'
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
  $3,
  writer_update.project_id,
  'writer.run.failed',
  next_sequence.sequence,
  $4::jsonb
FROM writer_update
JOIN workflow_update ON workflow_update.run_id = writer_update.run_id
CROSS JOIN next_sequence`

	if s.db != nil {
		tx, err := s.db.BeginTx(ctx, nil)
		if err != nil {
			return writerAdmissionFailed()
		}
		defer func() { _ = tx.Rollback() }()
		if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
			tenantID, strings.TrimSpace(input.ProjectID)); err != nil {
			return writerAdmissionFailed()
		}
		result, err := tx.ExecContext(ctx, query, tenantID, runID, WriterWorkflowType, string(payload))
		if err != nil {
			return writerAdmissionFailed()
		}
		if affected, rowsErr := result.RowsAffected(); rowsErr == nil && affected == 0 {
			// Already compensated or not queued — treat as success for idempotent retries.
			if err := tx.Commit(); err != nil {
				return writerAdmissionFailed()
			}
			return nil
		}
		if err := tx.Commit(); err != nil {
			return writerAdmissionFailed()
		}
		return nil
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "writer admission store is not configured"}
	}
	_, err = execAdmissionSQL(ctx, s.execer, tenantID, strings.TrimSpace(input.ProjectID), query,
		tenantID, runID, WriterWorkflowType, string(payload))
	if err != nil {
		return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "writer run compensation failed"}
	}
	return nil
}

func writerAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "writer run admission failed"}
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
