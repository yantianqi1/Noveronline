package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
)

type SQLAnalysisAdmissionStoreConfig struct {
	Execer WriterAdmissionSQLExecer
	DB     *sql.DB
}

type SQLAnalysisAdmissionStore struct {
	execer WriterAdmissionSQLExecer
	db     *sql.DB
}

func NewSQLAnalysisAdmissionStore(config SQLAnalysisAdmissionStoreConfig) *SQLAnalysisAdmissionStore {
	return &SQLAnalysisAdmissionStore{execer: config.Execer, db: config.DB}
}

func (s *SQLAnalysisAdmissionStore) AdmitAnalysisRun(ctx context.Context, input AnalysisAdmissionInput) (AnalysisRun, bool, error) {
	if missingAnalysisAdmissionContext(input) {
		return AnalysisRun{}, false, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, run_id, workflow_type, and upload_id are required",
		}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "queued"
	}
	mode := strings.TrimSpace(input.Mode)
	if mode == "" {
		mode = "full"
	}
	moduleKey := strings.TrimSpace(input.ModuleKey)
	if moduleKey == "" {
		moduleKey = "analysis_planner"
	}
	instruction := strings.TrimSpace(input.Instruction)
	if instruction == "" {
		instruction = "Analyze the uploaded novel into structured story knowledge."
	}
	proposed := AnalysisRun{
		RunID:        strings.TrimSpace(input.RunID),
		TraceID:      strings.TrimSpace(input.TraceID),
		TenantID:     strings.TrimSpace(input.TenantID),
		ProjectID:    strings.TrimSpace(input.ProjectID),
		WorkflowType: strings.TrimSpace(input.WorkflowType),
		Status:       status,
		Mode:         mode,
		Instruction:  instruction,
		UploadID:     strings.TrimSpace(input.UploadID),
		SourceFileID: strings.TrimSpace(input.SourceFileID),
	}
	if proposed.TraceID == "" {
		proposed.TraceID = traceIDForRun(proposed.RunID)
	}
	if s.db != nil {
		return s.admitWithDB(ctx, input, proposed, moduleKey)
	}
	if s.execer == nil {
		return AnalysisRun{}, false, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis admission store is not configured"}
	}
	if err := s.insertAdmission(ctx, input, proposed, moduleKey); err != nil {
		return AnalysisRun{}, false, err
	}
	return proposed, false, nil
}

func (s *SQLAnalysisAdmissionStore) admitWithDB(ctx context.Context, input AnalysisAdmissionInput, proposed AnalysisRun, moduleKey string) (AnalysisRun, bool, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return AnalysisRun{}, false, analysisAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
		proposed.TenantID, proposed.ProjectID); err != nil {
		return AnalysisRun{}, false, analysisAdmissionFailed()
	}
	if existing, found, replayErr := findAnalysisRunReplay(ctx, tx, input); replayErr != nil {
		return AnalysisRun{}, false, replayErr
	} else if found {
		if err := tx.Commit(); err != nil {
			return AnalysisRun{}, false, analysisAdmissionFailed()
		}
		return existing, true, nil
	}
	if err := insertAnalysisAdmissionTx(ctx, tx, input, proposed, moduleKey); err != nil {
		return AnalysisRun{}, false, err
	}
	if err := tx.Commit(); err != nil {
		return AnalysisRun{}, false, analysisAdmissionFailed()
	}
	return proposed, false, nil
}

func findAnalysisRunReplay(ctx context.Context, tx *sql.Tx, input AnalysisAdmissionInput) (AnalysisRun, bool, error) {
	requestID := strings.TrimSpace(input.RequestID)
	if requestID == "" {
		return AnalysisRun{}, false, nil
	}
	workflowType := strings.TrimSpace(input.WorkflowType)
	if workflowType == "" {
		workflowType = AnalysisWorkflowType
	}
	var run AnalysisRun
	err := tx.QueryRowContext(ctx, `
SELECT analysis.run_id::text,
  COALESCE(queued.payload_jsonb->>'trace_id', ''),
  analysis.project_id::text,
  analysis.mode,
  analysis.instruction,
  analysis.status,
  COALESCE(analysis.upload_id::text, ''),
  COALESCE(analysis.source_file_id::text, '')
FROM analysis_runs AS analysis
JOIN workflow_runs AS workflow
  ON workflow.tenant_id = analysis.tenant_id
 AND workflow.run_id = analysis.workflow_run_id
JOIN workflow_events AS queued
  ON queued.tenant_id = workflow.tenant_id
 AND queued.run_id = workflow.run_id
 AND queued.event_type = 'workflow.queued'
WHERE analysis.tenant_id = $1::uuid
  AND analysis.project_id = $2::uuid
  AND workflow.workflow_type = $3
  AND queued.payload_jsonb->>'request_id' = $4
ORDER BY analysis.created_at ASC
LIMIT 1`,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		workflowType,
		requestID,
	).Scan(
		&run.RunID,
		&run.TraceID,
		&run.ProjectID,
		&run.Mode,
		&run.Instruction,
		&run.Status,
		&run.UploadID,
		&run.SourceFileID,
	)
	if err == sql.ErrNoRows {
		return AnalysisRun{}, false, nil
	}
	if err != nil {
		return AnalysisRun{}, false, analysisAdmissionFailed()
	}
	run.TenantID = strings.TrimSpace(input.TenantID)
	run.WorkflowType = workflowType
	return run, true, nil
}

func (s *SQLAnalysisAdmissionStore) insertAdmission(ctx context.Context, input AnalysisAdmissionInput, proposed AnalysisRun, moduleKey string) error {
	hintsJSON, err := json.Marshal(sanitizeAnalysisHints(input.Hints))
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "analysis hints must be JSON serializable"}
	}
	optionsJSON, err := json.Marshal(sanitizeAnalysisOptions(input.Options))
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "analysis options must be JSON serializable"}
	}
	eventPayload, err := json.Marshal(map[string]any{
		"status":         proposed.Status,
		"workflow_type":  proposed.WorkflowType,
		"request_id":     strings.TrimSpace(input.RequestID),
		"trace_id":       proposed.TraceID,
		"upload_id":      proposed.UploadID,
		"source_file_id": proposed.SourceFileID,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "analysis admission payload must be JSON serializable"}
	}
	query := `WITH source_update AS (
  UPDATE source_files
  SET parse_status = 'parsing',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND upload_id = $10::uuid
    AND ($11 = '' OR file_id = $11::uuid)
    AND parse_status IN ('uploaded', 'failed', 'cancelled', 'parsed', 'parsing')
  RETURNING upload_id, file_id
),
workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message, started_by, temporal_workflow_id
  )
  SELECT $1::uuid, $3::uuid, $4, $2::uuid, $5, 0, $8, NULLIF($6, '')::uuid, $7
  FROM source_update
  RETURNING run_id
),
analysis_insert AS (
  INSERT INTO analysis_runs (
    tenant_id, run_id, workflow_run_id, project_id, source_file_id, upload_id,
    mode, status, module_key, instruction, hints_jsonb, options_jsonb, created_by
  )
  SELECT
    $1::uuid, $3::uuid, workflow_insert.run_id, $2::uuid,
    source_update.file_id, source_update.upload_id,
    $12, $5, $13, $14, $15::jsonb, $16::jsonb, NULLIF($6, '')::uuid
  FROM workflow_insert
  CROSS JOIN source_update
  RETURNING run_id
)
INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT
  $1::uuid, workflow_insert.run_id, $4, $2::uuid, 'workflow.queued', 1,
  $9::jsonb || jsonb_build_object('source_file_id', source_update.file_id::text)
FROM workflow_insert
CROSS JOIN source_update
CROSS JOIN analysis_insert`
	result, err := execAdmissionSQL(
		ctx,
		s.execer,
		proposed.TenantID,
		proposed.ProjectID,
		query,
		proposed.TenantID,
		proposed.ProjectID,
		proposed.RunID,
		proposed.WorkflowType,
		proposed.Status,
		strings.TrimSpace(input.ActorUserID),
		strings.TrimSpace(input.TemporalWorkflowID),
		"queued",
		string(eventPayload),
		proposed.UploadID,
		proposed.SourceFileID,
		proposed.Mode,
		moduleKey,
		proposed.Instruction,
		string(hintsJSON),
		string(optionsJSON),
	)
	if err != nil {
		return analysisAdmissionFailed()
	}
	if result == nil {
		return analysisAdmissionFailed()
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return analysisAdmissionFailed()
	}
	if rowsAffected == 0 {
		return sourceFileNotUploadedForSeed()
	}
	return nil
}

func insertAnalysisAdmissionTx(ctx context.Context, tx *sql.Tx, input AnalysisAdmissionInput, proposed AnalysisRun, moduleKey string) error {
	hintsJSON, err := json.Marshal(sanitizeAnalysisHints(input.Hints))
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "analysis hints must be JSON serializable"}
	}
	optionsJSON, err := json.Marshal(sanitizeAnalysisOptions(input.Options))
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "analysis options must be JSON serializable"}
	}
	eventPayload, err := json.Marshal(map[string]any{
		"status":         proposed.Status,
		"workflow_type":  proposed.WorkflowType,
		"request_id":     strings.TrimSpace(input.RequestID),
		"trace_id":       proposed.TraceID,
		"upload_id":      proposed.UploadID,
		"source_file_id": proposed.SourceFileID,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "analysis admission payload must be JSON serializable"}
	}
	var sourceFileID string
	err = tx.QueryRowContext(ctx, `
WITH source_update AS (
  UPDATE source_files
  SET parse_status = 'parsing',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND upload_id = $3::uuid
    AND ($4 = '' OR file_id = $4::uuid)
    AND parse_status IN ('uploaded', 'failed', 'cancelled', 'parsed', 'parsing')
  RETURNING upload_id, file_id
),
workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message, started_by, temporal_workflow_id
  )
  SELECT $1::uuid, $5::uuid, $6, $2::uuid, $7, 0, 'queued', NULLIF($8, '')::uuid, $9
  FROM source_update
  RETURNING run_id
),
analysis_insert AS (
  INSERT INTO analysis_runs (
    tenant_id, run_id, workflow_run_id, project_id, source_file_id, upload_id,
    mode, status, module_key, instruction, hints_jsonb, options_jsonb, created_by
  )
  SELECT
    $1::uuid, $5::uuid, workflow_insert.run_id, $2::uuid,
    source_update.file_id, source_update.upload_id,
    $10, $7, $11, $12, $13::jsonb, $14::jsonb, NULLIF($8, '')::uuid
  FROM workflow_insert
  CROSS JOIN source_update
  RETURNING source_file_id::text
)
INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT
  $1::uuid, $5::uuid, $6, $2::uuid, 'workflow.queued', 1,
  $15::jsonb || jsonb_build_object('source_file_id', analysis_insert.source_file_id)
FROM analysis_insert
RETURNING (SELECT source_file_id FROM analysis_insert)`,
		proposed.TenantID,
		proposed.ProjectID,
		proposed.UploadID,
		proposed.SourceFileID,
		proposed.RunID,
		proposed.WorkflowType,
		proposed.Status,
		strings.TrimSpace(input.ActorUserID),
		strings.TrimSpace(input.TemporalWorkflowID),
		proposed.Mode,
		moduleKey,
		proposed.Instruction,
		string(hintsJSON),
		string(optionsJSON),
		string(eventPayload),
	).Scan(&sourceFileID)
	if err == sql.ErrNoRows {
		return sourceFileNotUploadedForSeed()
	}
	if err != nil {
		return analysisAdmissionFailed()
	}
	if sourceFileID != "" {
		proposed.SourceFileID = sourceFileID
	}
	return nil
}

func (s *SQLAnalysisAdmissionStore) CompensateAnalysisRunStart(ctx context.Context, input AnalysisCompensationInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.RunID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and run_id are required"}
	}
	if s.execer == nil && s.db == nil {
		return &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "analysis admission store is not configured"}
	}
	payload, err := json.Marshal(map[string]any{
		"status":        "failed",
		"workflow_type": AnalysisWorkflowType,
		"request_id":    strings.TrimSpace(input.RequestID),
		"trace_id":      strings.TrimSpace(input.TraceID),
		"error_code":    "WORKFLOW_FAILED",
		"error_message": "failed to start analysis_run workflow",
	})
	if err != nil {
		return analysisAdmissionFailed()
	}
	query := `
WITH workflow_update AS (
  UPDATE workflow_runs
  SET status = 'failed',
      error_code = 'WORKFLOW_FAILED',
      error_message = 'failed to start analysis_run workflow',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND run_id = $3::uuid
    AND workflow_type = $4
  RETURNING run_id
),
analysis_update AS (
  UPDATE analysis_runs
  SET status = 'failed',
      error_code = 'WORKFLOW_FAILED',
      error_message = 'failed to start analysis_run workflow',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND run_id = $3::uuid
  RETURNING run_id
),
source_update AS (
  UPDATE source_files
  SET parse_status = 'uploaded',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND ($5 = '' OR upload_id = $5::uuid)
    AND ($6 = '' OR file_id = $6::uuid)
    AND parse_status = 'parsing'
  RETURNING file_id
)
INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT
  $1::uuid, $3::uuid, $4, $2::uuid, 'workflow.failed',
  COALESCE((SELECT MAX(sequence) FROM workflow_events WHERE tenant_id = $1::uuid AND run_id = $3::uuid), 0) + 1,
  $7::jsonb || CASE
    WHEN EXISTS (SELECT 1 FROM source_update)
    THEN jsonb_build_object('source_file_id', (SELECT file_id::text FROM source_update LIMIT 1))
    ELSE '{}'::jsonb
  END
FROM workflow_update
CROSS JOIN analysis_update`
	_, err = execAdmissionSQL(
		ctx,
		s.preferExecer(),
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RunID),
		AnalysisWorkflowType,
		strings.TrimSpace(input.UploadID),
		strings.TrimSpace(input.SourceFileID),
		string(payload),
	)
	if err != nil {
		return analysisAdmissionFailed()
	}
	return nil
}

func (s *SQLAnalysisAdmissionStore) CancelAnalysisRun(ctx context.Context, input AnalysisCancellationInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	status := strings.TrimSpace(input.Status)
	if status == "" {
		status = "cancelled"
	}
	query := `
WITH workflow_update AS (
  UPDATE workflow_runs
  SET status = $3,
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND run_id = $2::uuid
    AND workflow_type = $4
  RETURNING run_id, project_id
),
analysis_update AS (
  UPDATE analysis_runs
  SET status = $3,
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND run_id = $2::uuid
  RETURNING run_id, project_id, upload_id, source_file_id
),
source_release AS (
  UPDATE source_files
  SET parse_status = 'uploaded',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id IN (SELECT project_id FROM analysis_update)
    AND parse_status = 'parsing'
    AND (
      upload_id IN (SELECT upload_id FROM analysis_update WHERE upload_id IS NOT NULL)
      OR file_id IN (SELECT source_file_id FROM analysis_update WHERE source_file_id IS NOT NULL)
    )
  RETURNING file_id
)
INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT
  $1::uuid, workflow_update.run_id, $4, workflow_update.project_id, 'analysis.run.cancelled',
  COALESCE((SELECT MAX(sequence) FROM workflow_events WHERE tenant_id = $1::uuid AND run_id = $2::uuid), 0) + 1,
  jsonb_build_object('status', $3, 'request_id', $5)
FROM workflow_update
CROSS JOIN analysis_update`
	_, err := execAdmissionSQL(
		ctx,
		s.preferExecer(),
		strings.TrimSpace(input.TenantID),
		"",
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
		status,
		AnalysisWorkflowType,
		strings.TrimSpace(input.RequestID),
	)
	if err != nil {
		return analysisAdmissionFailed()
	}
	return nil
}

func (s *SQLAnalysisAdmissionStore) preferExecer() WriterAdmissionSQLExecer {
	if s.execer != nil {
		return s.execer
	}
	if s.db != nil {
		return NewSQLDBWriterAdmissionExecer(s.db)
	}
	return nil
}

func missingAnalysisAdmissionContext(input AnalysisAdmissionInput) bool {
	return strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == "" ||
		strings.TrimSpace(input.UploadID) == ""
}

func analysisAdmissionFailed() error {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "failed to persist analysis_run admission"}
}
