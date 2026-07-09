package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const seedWorkflowRetryStartFailedMessage = "failed to retry seed_pipeline workflow"

type RetryWorkflowRunInput struct {
	TenantID    string
	RunID       string
	ActorUserID string
	RequestID   string
}

type WorkflowRunRetry struct {
	RunID  string
	Status string
}

type WorkflowRetrier interface {
	RetryWorkflowRun(context.Context, RetryWorkflowRunInput) (WorkflowRunRetry, error)
}

type WorkflowRetryTargetInput struct {
	TenantID string
	RunID    string
}

type WorkflowRetryTarget struct {
	RunID           string
	ProjectID       string
	WorkflowType    string
	Status          string
	UploadID        string
	SourceFileID    string
	SourceObjectKey string
	SourceFilename  string
	SourceMimeType  string
	SourceSizeBytes int64
	SourceSHA256    string
}

type WorkflowRetryAdmissionInput struct {
	TenantID           string
	ProjectID          string
	RunID              string
	WorkflowType       string
	TemporalWorkflowID string
	ActorUserID        string
	RequestID          string
	UploadID           string
	SourceFileID       string
	PublicPayload      []any
}

type WorkflowRetryFailureInput struct {
	TenantID     string
	ProjectID    string
	RunID        string
	WorkflowType string
	ActorUserID  string
	RequestID    string
	UploadID     string
	SourceFileID string
	ErrorCode    string
	ErrorMessage string
}

type WorkflowRetryStore interface {
	GetWorkflowRetryTarget(context.Context, WorkflowRetryTargetInput) (WorkflowRetryTarget, error)
	AdmitWorkflowRetry(context.Context, WorkflowRetryAdmissionInput) error
	RecordWorkflowRetryStartFailure(context.Context, WorkflowRetryFailureInput) error
}

type DisabledWorkflowRetrier struct{}

func NewDisabledWorkflowRetrier() *DisabledWorkflowRetrier {
	return &DisabledWorkflowRetrier{}
}

func (r *DisabledWorkflowRetrier) RetryWorkflowRun(_ context.Context, _ RetryWorkflowRunInput) (WorkflowRunRetry, error) {
	return WorkflowRunRetry{}, &AppError{
		Code:    "WORKFLOW_RETRY_BACKEND_UNCONFIGURED",
		Message: "workflow retry backend is not configured",
	}
}

type TemporalWorkflowRetrierConfig struct {
	Client    TemporalWorkflowClient
	Store     WorkflowRetryStore
	TaskQueue string
}

type TemporalWorkflowRetrier struct {
	client    TemporalWorkflowClient
	store     WorkflowRetryStore
	taskQueue string
}

func NewTemporalWorkflowRetrier(config TemporalWorkflowRetrierConfig) *TemporalWorkflowRetrier {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = SeedTaskQueue
	}
	return &TemporalWorkflowRetrier{client: config.Client, store: config.Store, taskQueue: taskQueue}
}

func (r *TemporalWorkflowRetrier) RetryWorkflowRun(ctx context.Context, input RetryWorkflowRunInput) (WorkflowRunRetry, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	runID := strings.TrimSpace(input.RunID)
	if tenantID == "" || runID == "" {
		return WorkflowRunRetry{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if r.client == nil || r.store == nil {
		return WorkflowRunRetry{}, &AppError{Code: "WORKFLOW_RETRY_BACKEND_UNCONFIGURED", Message: "workflow retry backend is not configured"}
	}
	target, err := r.store.GetWorkflowRetryTarget(ctx, WorkflowRetryTargetInput{TenantID: tenantID, RunID: runID})
	if err != nil {
		return WorkflowRunRetry{}, err
	}
	if strings.TrimSpace(target.WorkflowType) != SeedWorkflowType || !seedRetryableStatus(target.Status) {
		return WorkflowRunRetry{}, &AppError{Code: "WORKFLOW_RETRY_NOT_ALLOWED", Message: "workflow run is not retryable"}
	}
	if err := validateSeedSourceHandoff(StartSeedRunInput{
		SourceFileID:    target.SourceFileID,
		SourceObjectKey: target.SourceObjectKey,
		SourceFilename:  target.SourceFilename,
		SourceMimeType:  target.SourceMimeType,
		SourceSizeBytes: target.SourceSizeBytes,
		SourceSHA256:    target.SourceSHA256,
	}); err != nil {
		return WorkflowRunRetry{}, err
	}
	actorUserID := strings.TrimSpace(input.ActorUserID)
	requestID := strings.TrimSpace(input.RequestID)
	traceID := traceIDForRun(runID)
	publicPayload := []any{
		"status", "retry_requested",
		"workflow_type", SeedWorkflowType,
		"request_id", requestID,
		"trace_id", traceID,
		"upload_id", strings.TrimSpace(target.UploadID),
		"source_file_id", strings.TrimSpace(target.SourceFileID),
	}
	temporalWorkflowID := "seed_run_" + runID + "_retry"
	if err := r.store.AdmitWorkflowRetry(ctx, WorkflowRetryAdmissionInput{
		TenantID:           tenantID,
		ProjectID:          strings.TrimSpace(target.ProjectID),
		RunID:              runID,
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: temporalWorkflowID,
		ActorUserID:        actorUserID,
		RequestID:          requestID,
		UploadID:           strings.TrimSpace(target.UploadID),
		SourceFileID:       strings.TrimSpace(target.SourceFileID),
		PublicPayload:      publicPayload,
	}); err != nil {
		return WorkflowRunRetry{}, err
	}
	payload := seedRetryTemporalPayload(tenantID, target, actorUserID, requestID, traceID)
	if _, err := r.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                r.taskQueue,
		WorkflowExecutionTimeout: 24 * time.Hour,
		WorkflowRunTimeout:       24 * time.Hour,
	}, SeedWorkflowName, payload); err != nil {
		failureErr := r.store.RecordWorkflowRetryStartFailure(ctx, WorkflowRetryFailureInput{
			TenantID:     tenantID,
			ProjectID:    strings.TrimSpace(target.ProjectID),
			RunID:        runID,
			WorkflowType: SeedWorkflowType,
			ActorUserID:  actorUserID,
			RequestID:    requestID,
			UploadID:     strings.TrimSpace(target.UploadID),
			SourceFileID: strings.TrimSpace(target.SourceFileID),
			ErrorCode:    "WORKFLOW_RETRY_FAILED",
			ErrorMessage: seedWorkflowRetryStartFailedMessage,
		})
		if failureErr != nil {
			return WorkflowRunRetry{}, workflowRetryFailed()
		}
		return WorkflowRunRetry{}, workflowRetryFailed()
	}
	return WorkflowRunRetry{RunID: runID, Status: "retry_requested"}, nil
}

type SQLWorkflowRetryStoreConfig struct {
	Queryer WriterEventSQLQueryer
	Execer  WriterAdmissionSQLExecer
}

type SQLWorkflowRetryStore struct {
	queryer WriterEventSQLQueryer
	execer  WriterAdmissionSQLExecer
}

func NewSQLWorkflowRetryStore(config SQLWorkflowRetryStoreConfig) *SQLWorkflowRetryStore {
	return &SQLWorkflowRetryStore{queryer: config.Queryer, execer: config.Execer}
}

func (s *SQLWorkflowRetryStore) GetWorkflowRetryTarget(ctx context.Context, input WorkflowRetryTargetInput) (WorkflowRetryTarget, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	runID := strings.TrimSpace(input.RunID)
	if tenantID == "" || runID == "" {
		return WorkflowRetryTarget{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if s.queryer == nil {
		return WorkflowRetryTarget{}, &AppError{Code: "WORKFLOW_RETRY_BACKEND_UNCONFIGURED", Message: "workflow retry backend is not configured"}
	}
	query := `WITH seed_source AS (
  SELECT
    payload_jsonb->>'upload_id' AS upload_id,
    payload_jsonb->>'source_file_id' AS source_file_id
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND run_id::text = $2
    AND event_type = 'workflow.queued'
  ORDER BY sequence ASC
  LIMIT 1
)
SELECT
  workflow_runs.run_id::text,
  workflow_runs.project_id::text,
  workflow_runs.workflow_type,
  workflow_runs.status,
  COALESCE(seed_source.upload_id, ''),
  COALESCE(source_files.file_id::text, ''),
  COALESCE(source_files.object_key, ''),
  COALESCE(source_files.filename, ''),
  COALESCE(source_files.mime_type, ''),
  COALESCE(source_files.size_bytes, 0),
  COALESCE(source_files.sha256, '')
FROM workflow_runs
LEFT JOIN seed_source ON true
LEFT JOIN source_files
  ON source_files.tenant_id = workflow_runs.tenant_id
 AND source_files.project_id = workflow_runs.project_id
 AND source_files.upload_id::text = seed_source.upload_id
 AND source_files.file_id::text = seed_source.source_file_id
WHERE workflow_runs.tenant_id::text = $1
  AND workflow_runs.run_id::text = $2
LIMIT 1`
	rows, err := queryWorkflowRetryRows(ctx, s.queryer, tenantID, query, tenantID, runID)
	if err != nil {
		return WorkflowRetryTarget{}, workflowRetryQueryFailed()
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return WorkflowRetryTarget{}, workflowRetryQueryFailed()
		}
		return WorkflowRetryTarget{}, &AppError{Code: "NOT_FOUND", Message: "workflow run not found"}
	}
	var target WorkflowRetryTarget
	var sourceSizeBytes sql.NullInt64
	if err := rows.Scan(
		&target.RunID,
		&target.ProjectID,
		&target.WorkflowType,
		&target.Status,
		&target.UploadID,
		&target.SourceFileID,
		&target.SourceObjectKey,
		&target.SourceFilename,
		&target.SourceMimeType,
		&sourceSizeBytes,
		&target.SourceSHA256,
	); err != nil {
		return WorkflowRetryTarget{}, workflowRetryQueryFailed()
	}
	if sourceSizeBytes.Valid {
		target.SourceSizeBytes = sourceSizeBytes.Int64
	}
	if err := rows.Err(); err != nil {
		return WorkflowRetryTarget{}, workflowRetryQueryFailed()
	}
	return target, nil
}

func (s *SQLWorkflowRetryStore) AdmitWorkflowRetry(ctx context.Context, input WorkflowRetryAdmissionInput) error {
	if missingWorkflowRetryContext(input.TenantID, input.ProjectID, input.RunID, input.WorkflowType, input.TemporalWorkflowID, input.UploadID, input.SourceFileID) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, temporal_workflow_id, upload_id, and source_file_id are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_RETRY_BACKEND_UNCONFIGURED", Message: "workflow retry backend is not configured"}
	}
	payload, err := retryPublicPayloadJSON(input.PublicPayload, map[string]any{
		"status":         "retry_requested",
		"workflow_type":  strings.TrimSpace(input.WorkflowType),
		"request_id":     strings.TrimSpace(input.RequestID),
		"actor_user_id":  strings.TrimSpace(input.ActorUserID),
		"upload_id":      strings.TrimSpace(input.UploadID),
		"source_file_id": strings.TrimSpace(input.SourceFileID),
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "workflow retry payload must be JSON serializable"}
	}
	query := `WITH source_update AS (
  UPDATE source_files
  SET parse_status = 'parsing',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND upload_id = $5::uuid
    AND file_id = $6::uuid
    AND parse_status IN ('uploaded', 'failed', 'cancelled', 'parsed')
    AND EXISTS (
      SELECT 1
      FROM workflow_runs
      WHERE workflow_runs.tenant_id = $1::uuid
        AND workflow_runs.project_id = $2::uuid
        AND workflow_runs.run_id = $3::uuid
        AND workflow_runs.workflow_type = $4
        AND workflow_runs.workflow_type = 'seed_pipeline'
        AND workflow_runs.status IN ('failed', 'cancelled')
    )
  RETURNING file_id
),
workflow_update AS (
  UPDATE workflow_runs
  SET
    status = 'queued',
    progress = 0,
    message = 'retry requested',
    error_code = NULL,
    error_message = NULL,
    result_jsonb = NULL,
    temporal_workflow_id = $7,
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND run_id = $3::uuid
    AND workflow_type = $4
    AND workflow_type = 'seed_pipeline'
    AND status IN ('failed', 'cancelled')
    AND EXISTS (SELECT 1 FROM source_update)
  RETURNING run_id, project_id, workflow_type
),
retry_admission_guard AS (
  SELECT CASE
    WHEN (SELECT COUNT(*) FROM source_update) = 1
     AND (SELECT COUNT(*) FROM workflow_update) = 1
    THEN 1
    ELSE 1 / 0
  END AS ok
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
  'workflow.retry_requested',
  next_sequence.sequence,
  $8::jsonb
FROM retry_admission_guard
CROSS JOIN workflow_update
CROSS JOIN source_update
CROSS JOIN next_sequence`
	result, err := execAdmissionSQL(ctx, s.execer, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.WorkflowType),
		strings.TrimSpace(input.UploadID),
		strings.TrimSpace(input.SourceFileID),
		strings.TrimSpace(input.TemporalWorkflowID),
		string(payload),
	)
	if err != nil || result == nil {
		return workflowRetryAdmissionFailed()
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected == 0 {
		return workflowRetryAdmissionFailed()
	}
	return nil
}

func (s *SQLWorkflowRetryStore) RecordWorkflowRetryStartFailure(ctx context.Context, input WorkflowRetryFailureInput) error {
	if missingWorkflowRetryContext(input.TenantID, input.ProjectID, input.RunID, input.WorkflowType, input.UploadID, input.SourceFileID) {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, workflow_type, upload_id, and source_file_id are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_RETRY_BACKEND_UNCONFIGURED", Message: "workflow retry backend is not configured"}
	}
	errorCode := "WORKFLOW_RETRY_FAILED"
	errorMessage := seedWorkflowRetryStartFailedMessage
	payload, err := json.Marshal(map[string]any{
		"status":         "failed",
		"workflow_type":  strings.TrimSpace(input.WorkflowType),
		"request_id":     strings.TrimSpace(input.RequestID),
		"actor_user_id":  strings.TrimSpace(input.ActorUserID),
		"upload_id":      strings.TrimSpace(input.UploadID),
		"source_file_id": strings.TrimSpace(input.SourceFileID),
		"error_code":     errorCode,
		"error_message":  errorMessage,
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "workflow retry failure payload must be JSON serializable"}
	}
	query := `WITH workflow_update AS (
  UPDATE workflow_runs
  SET
    status = 'failed',
    message = $7,
    error_code = $8,
    error_message = $7,
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND run_id = $3::uuid
    AND workflow_type = $4
    AND workflow_type = 'seed_pipeline'
    AND status = 'queued'
  RETURNING run_id, project_id, workflow_type
),
source_update AS (
  UPDATE source_files
  SET parse_status = 'uploaded',
      updated_at = now()
  WHERE tenant_id = $1::uuid
    AND project_id = $2::uuid
    AND upload_id = $5::uuid
    AND file_id = $6::uuid
    AND parse_status = 'parsing'
    AND EXISTS (SELECT 1 FROM workflow_update)
  RETURNING file_id
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
  $9::jsonb
FROM workflow_update
CROSS JOIN next_sequence
LEFT JOIN source_update ON TRUE`
	result, err := execAdmissionSQL(ctx, s.execer, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.WorkflowType),
		strings.TrimSpace(input.UploadID),
		strings.TrimSpace(input.SourceFileID),
		errorMessage,
		errorCode,
		string(payload),
	)
	if err != nil || result == nil {
		return workflowRetryFailed()
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected == 0 {
		return workflowRetryFailed()
	}
	return nil
}

func seedRetryTemporalPayload(tenantID string, target WorkflowRetryTarget, actorUserID string, requestID string, traceID string) map[string]any {
	projectID := strings.TrimSpace(target.ProjectID)
	runID := strings.TrimSpace(target.RunID)
	return map[string]any{
		"context": map[string]any{
			"tenant_id":     tenantID,
			"project_id":    projectID,
			"run_id":        runID,
			"workflow_type": SeedWorkflowType,
			"actor_user_id": actorUserID,
			"trace_id":      traceID,
			"permissions": map[string][]string{
				"seed_pipeline": {"run"},
			},
		},
		"tenant_id":         tenantID,
		"project_id":        projectID,
		"run_id":            runID,
		"workflow_type":     SeedWorkflowType,
		"actor_user_id":     actorUserID,
		"request_id":        requestID,
		"trace_id":          traceID,
		"upload_id":         strings.TrimSpace(target.UploadID),
		"source_file_id":    strings.TrimSpace(target.SourceFileID),
		"source_object_key": strings.TrimSpace(target.SourceObjectKey),
		"source_filename":   strings.TrimSpace(target.SourceFilename),
		"source_mime_type":  strings.TrimSpace(target.SourceMimeType),
		"source_size_bytes": target.SourceSizeBytes,
		"source_sha256":     strings.TrimSpace(target.SourceSHA256),
		"options":           map[string]any{},
		"permissions": map[string][]string{
			"seed_pipeline": {"run"},
		},
	}
}

func seedRetryableStatus(status string) bool {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "failed", "cancelled":
		return true
	default:
		return false
	}
}

func queryWorkflowRetryRows(ctx context.Context, queryer WriterEventSQLQueryer, tenantID string, query string, args ...any) (WriterEventSQLRows, error) {
	if tenantQueryer, ok := queryer.(WriterEventSQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return queryer.QueryContext(ctx, query, args...)
}

func retryPublicPayloadJSON(publicPayload []any, fallback map[string]any) ([]byte, error) {
	payload := map[string]any{}
	for index := 0; index+1 < len(publicPayload); index += 2 {
		key, ok := publicPayload[index].(string)
		if !ok || isSensitiveWorkflowPayloadKey(key) {
			continue
		}
		payload[key] = publicPayload[index+1]
	}
	for key, value := range fallback {
		if _, ok := payload[key]; !ok && !isSensitiveWorkflowPayloadKey(key) {
			payload[key] = value
		}
	}
	return json.Marshal(SanitizeWorkflowEventPayload(payload))
}

func missingWorkflowRetryContext(values ...string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return true
		}
	}
	return false
}

func workflowRetryQueryFailed() *AppError {
	return &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: "workflow retry query failed"}
}

func workflowRetryAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_RETRY_FAILED", Message: "workflow retry admission failed"}
}

func workflowRetryFailed() *AppError {
	return &AppError{Code: "WORKFLOW_RETRY_FAILED", Message: seedWorkflowRetryStartFailedMessage}
}
