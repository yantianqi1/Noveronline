package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	seedWorkflowRetryStartFailedMessage = "failed to retry seed_pipeline workflow"
	seedSegmentRetryStartFailedMessage  = "failed to start seed segment retry workflow"

	SeedSegmentRetryWorkflowName = "SeedSegmentRetryWorkflow"
)

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

type RetrySeedSegmentsInput struct {
	TenantID    string
	ProjectID   string
	RunID       string
	SegmentIDs  []string
	ActorUserID string
	RequestID   string
}

type SeedSegmentsRetry struct {
	RunID          string
	Status         string
	RequestedCount int
}

type SeedSegmentRetrier interface {
	RetrySeedSegments(context.Context, RetrySeedSegmentsInput) (SeedSegmentsRetry, error)
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
	FailedStage     string
	Segments        []SeedRetrySegment
}

type SeedRetrySegment struct {
	SegmentID    string `json:"segment_id"`
	SegmentOrder int    `json:"segment_order"`
	ObjectKey    string `json:"object_key"`
	ChapterGuess string `json:"chapter_guess,omitempty"`
	TitleGuess   string `json:"title_guess,omitempty"`
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
	ResumeStage        string
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

type DisabledSeedSegmentRetrier struct{}

func NewDisabledSeedSegmentRetrier() *DisabledSeedSegmentRetrier {
	return &DisabledSeedSegmentRetrier{}
}

func (r *DisabledSeedSegmentRetrier) RetrySeedSegments(_ context.Context, _ RetrySeedSegmentsInput) (SeedSegmentsRetry, error) {
	return SeedSegmentsRetry{}, &AppError{
		Code:    "SEED_SEGMENT_RETRY_BACKEND_UNCONFIGURED",
		Message: "seed segment retry backend is not configured",
	}
}

type SQLSeedSegmentRetrierConfig struct {
	Execer    WriterAdmissionSQLExecer
	Client    TemporalWorkflowClient
	TaskQueue string
}

type SQLSeedSegmentRetrier struct {
	execer    WriterAdmissionSQLExecer
	client    TemporalWorkflowClient
	taskQueue string
}

func NewSQLSeedSegmentRetrier(config SQLSeedSegmentRetrierConfig) *SQLSeedSegmentRetrier {
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = SeedTaskQueue
	}
	return &SQLSeedSegmentRetrier{
		execer:    config.Execer,
		client:    config.Client,
		taskQueue: taskQueue,
	}
}

func (r *SQLSeedSegmentRetrier) RetrySeedSegments(ctx context.Context, input RetrySeedSegmentsInput) (SeedSegmentsRetry, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	runID := strings.TrimSpace(input.RunID)
	segmentIDs := normalizeSeedSegmentRetryIDs(input.SegmentIDs)
	if !validSeedSegmentRetryContext(tenantID, projectID, runID, strings.TrimSpace(input.ActorUserID), segmentIDs) {
		return SeedSegmentsRetry{}, &AppError{Code: "VALIDATION_FAILED", Message: "seed segment retry context is invalid"}
	}
	if r.execer == nil || r.client == nil {
		return SeedSegmentsRetry{}, &AppError{Code: "SEED_SEGMENT_RETRY_BACKEND_UNCONFIGURED", Message: "seed segment retry backend is not configured"}
	}
	executionID, err := newRunID()
	if err != nil {
		return SeedSegmentsRetry{}, seedSegmentRetryFailed()
	}
	segmentIDsJSON, err := json.Marshal(segmentIDs)
	if err != nil {
		return SeedSegmentsRetry{}, &AppError{Code: "VALIDATION_FAILED", Message: "seed segment retry payload must be JSON serializable"}
	}
	eventPayload, err := json.Marshal(SanitizeWorkflowEventPayload(map[string]any{
		"status":          "retry_requested",
		"workflow_type":   SeedWorkflowType,
		"request_id":      strings.TrimSpace(input.RequestID),
		"requested_count": len(segmentIDs),
	}))
	if err != nil {
		return SeedSegmentsRetry{}, &AppError{Code: "VALIDATION_FAILED", Message: "seed segment retry event payload must be JSON serializable"}
	}
	query := `WITH requested_segments AS (
  SELECT DISTINCT value::uuid AS segment_id
  FROM jsonb_array_elements_text($4::jsonb) AS value
),
seed_run AS (
  SELECT workflow_runs.run_id, workflow_runs.project_id, workflow_runs.workflow_type
  FROM workflow_runs
  WHERE workflow_runs.tenant_id = $1::uuid
    AND workflow_runs.project_id = $2::uuid
    AND workflow_runs.run_id = $3::uuid
    AND workflow_runs.workflow_type = 'seed_pipeline'
    AND workflow_runs.status IN ('failed', 'cancelled')
),
segment_scope AS (
  SELECT text_segments.segment_id
  FROM text_segments
  JOIN requested_segments
    ON requested_segments.segment_id = text_segments.segment_id
  WHERE text_segments.tenant_id = $1::uuid
    AND text_segments.project_id = $2::uuid
    AND text_segments.run_id = $3::uuid
    AND EXISTS (SELECT 1 FROM seed_run)
),
active_retry_conflicts AS (
  SELECT retry_requests.segment_id
  FROM seed_segment_retry_requests AS retry_requests
  JOIN requested_segments
    ON requested_segments.segment_id = retry_requests.segment_id
  WHERE retry_requests.tenant_id = $1::uuid
    AND retry_requests.project_id = $2::uuid
    AND retry_requests.run_id = $3::uuid
    AND retry_requests.status IN ('requested', 'running')
),
segment_retry_guard AS (
  SELECT
    (SELECT COUNT(*) FROM requested_segments) > 0
    AND (SELECT COUNT(*) FROM segment_scope) = (SELECT COUNT(*) FROM requested_segments) AS ok
),
active_retry_guard AS (
  SELECT (SELECT COUNT(*) FROM active_retry_conflicts) = 0 AS ok
),
upserted AS (
  INSERT INTO seed_segment_retry_requests (
    tenant_id,
    project_id,
    run_id,
    segment_id,
    status,
    requested_by,
    request_id,
    retry_attempt_id,
    requested_at,
    updated_at
  )
  SELECT
    $1::uuid,
    $2::uuid,
    $3::uuid,
    segment_scope.segment_id,
    'requested',
    NULLIF($5, '')::uuid,
    NULLIF($6, ''),
    $7::uuid,
    now(),
    now()
  FROM segment_retry_guard
  CROSS JOIN active_retry_guard
  CROSS JOIN segment_scope
  WHERE segment_retry_guard.ok
    AND active_retry_guard.ok
  ON CONFLICT (tenant_id, run_id, segment_id)
  DO UPDATE SET
    status = 'requested',
    requested_by = EXCLUDED.requested_by,
    request_id = EXCLUDED.request_id,
    retry_attempt_id = EXCLUDED.retry_attempt_id,
    requested_at = EXCLUDED.requested_at,
    updated_at = now()
  WHERE seed_segment_retry_requests.status IN ('completed', 'failed', 'cancelled')
  RETURNING segment_id
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
  seed_run.run_id,
  seed_run.workflow_type,
  seed_run.project_id,
  'seed.segments.retry_requested',
  next_sequence.sequence,
  $8::jsonb
FROM seed_run
CROSS JOIN next_sequence
WHERE (SELECT COUNT(*) FROM upserted) = (SELECT COUNT(*) FROM requested_segments)`
	result, err := execAdmissionSQL(ctx, r.execer, tenantID, projectID, query,
		tenantID,
		projectID,
		runID,
		string(segmentIDsJSON),
		strings.TrimSpace(input.ActorUserID),
		strings.TrimSpace(input.RequestID),
		executionID,
		string(eventPayload),
	)
	if err != nil || result == nil {
		return SeedSegmentsRetry{}, seedSegmentRetryFailed()
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected == 0 {
		return SeedSegmentsRetry{}, seedSegmentRetryFailed()
	}
	temporalWorkflowID := "seed_segment_retry_" + runID + "_" + executionID
	traceID := traceIDForRun(runID)
	payload := seedSegmentRetryTemporalPayload(input, tenantID, projectID, runID, segmentIDs, traceID)
	payload["retry_attempt_id"] = executionID
	if _, err := r.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       temporalWorkflowID,
		TaskQueue:                r.taskQueue,
		WorkflowExecutionTimeout: time.Hour,
		WorkflowRunTimeout:       time.Hour,
	}, SeedSegmentRetryWorkflowName, payload); err != nil {
		compensationCtx, cancelCompensation := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
		compensationErr := r.recordSeedSegmentRetryStartFailure(
			compensationCtx,
			tenantID,
			projectID,
			runID,
			segmentIDs,
			executionID,
			strings.TrimSpace(input.RequestID),
		)
		cancelCompensation()
		if compensationErr != nil {
			return SeedSegmentsRetry{}, seedSegmentRetryFailed()
		}
		return SeedSegmentsRetry{}, seedSegmentRetryFailed()
	}
	return SeedSegmentsRetry{
		RunID:          runID,
		Status:         "retry_requested",
		RequestedCount: len(segmentIDs),
	}, nil
}

func (r *SQLSeedSegmentRetrier) recordSeedSegmentRetryStartFailure(
	ctx context.Context,
	tenantID string,
	projectID string,
	runID string,
	segmentIDs []string,
	retryAttemptID string,
	requestID string,
) error {
	segmentIDsJSON, err := json.Marshal(segmentIDs)
	if err != nil {
		return seedSegmentRetryFailed()
	}
	eventPayload, err := json.Marshal(SanitizeWorkflowEventPayload(map[string]any{
		"status":          "failed",
		"workflow_type":   SeedWorkflowType,
		"request_id":      requestID,
		"requested_count": len(segmentIDs),
		"error_code":      "SEED_SEGMENT_RETRY_FAILED",
		"error_message":   seedSegmentRetryStartFailedMessage,
	}))
	if err != nil {
		return seedSegmentRetryFailed()
	}
	query := `WITH retry_context AS (
  SELECT
    $1::uuid AS tenant_id,
    $2::uuid AS project_id,
    $3::uuid AS run_id,
    $4::jsonb AS segment_ids
),
requested_segments AS (
  SELECT DISTINCT value::uuid AS segment_id
  FROM retry_context,
       jsonb_array_elements_text(retry_context.segment_ids) AS value
),
eligible_retries AS (
  SELECT retry_requests.segment_id
  FROM seed_segment_retry_requests AS retry_requests
  JOIN requested_segments
    ON requested_segments.segment_id = retry_requests.segment_id
  WHERE retry_requests.tenant_id = $1::uuid
    AND retry_requests.project_id = $2::uuid
    AND retry_requests.run_id = $3::uuid
    AND retry_requests.status = 'requested'
    AND retry_requests.retry_attempt_id = $6::uuid
),
retry_guard AS (
  SELECT
    (SELECT COUNT(*) FROM requested_segments) AS requested_count,
    (SELECT COUNT(*) FROM eligible_retries) AS eligible_count
),
failed_retries AS (
  UPDATE seed_segment_retry_requests AS retry_requests
  SET status = 'failed',
      last_error_code = 'SEED_SEGMENT_RETRY_FAILED',
      last_error_message = $5,
      updated_at = now()
  FROM eligible_retries, retry_guard
  WHERE retry_requests.tenant_id = $1::uuid
    AND retry_requests.project_id = $2::uuid
    AND retry_requests.run_id = $3::uuid
    AND retry_requests.segment_id = eligible_retries.segment_id
    AND retry_guard.requested_count = retry_guard.eligible_count
  RETURNING retry_requests.segment_id
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
  workflow_runs.run_id,
  workflow_runs.workflow_type,
  workflow_runs.project_id,
  'seed.segments.retry_failed',
  next_sequence.sequence,
  $7::jsonb
FROM workflow_runs
CROSS JOIN next_sequence
WHERE workflow_runs.tenant_id = $1::uuid
  AND workflow_runs.project_id = $2::uuid
  AND workflow_runs.run_id = $3::uuid
  AND workflow_runs.workflow_type = 'seed_pipeline'
  AND (SELECT COUNT(*) FROM failed_retries) = (SELECT COUNT(*) FROM requested_segments)`
	result, err := execAdmissionSQL(
		ctx,
		r.execer,
		tenantID,
		projectID,
		query,
		tenantID,
		projectID,
		runID,
		string(segmentIDsJSON),
		seedSegmentRetryStartFailedMessage,
		retryAttemptID,
		string(eventPayload),
	)
	if err != nil || result == nil {
		return seedSegmentRetryFailed()
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected == 0 {
		return seedSegmentRetryFailed()
	}
	return nil
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
		"retry_from_stage", retryFromStage(target),
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
		ResumeStage:        retryFromStage(target),
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
),
failed_stage AS (
  SELECT payload_jsonb->>'stage' AS stage
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND run_id::text = $2
    AND event_type = 'seed.stage.failed'
  ORDER BY sequence DESC
  LIMIT 1
),
retry_segments AS (
  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'segment_id', segment_id::text,
        'segment_order', segment_order,
        'object_key', object_key,
        'chapter_guess', chapter_guess,
        'title_guess', title_guess
      ) ORDER BY segment_order
    ),
    '[]'::jsonb
  )::text AS segments_json
  FROM text_segments
  WHERE tenant_id::text = $1
    AND run_id::text = $2
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
  COALESCE(source_files.sha256, ''),
  COALESCE(failed_stage.stage, ''),
  retry_segments.segments_json
FROM workflow_runs
LEFT JOIN seed_source ON true
LEFT JOIN failed_stage ON true
LEFT JOIN retry_segments ON true
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
	var segmentsJSON string
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
		&target.FailedStage,
		&segmentsJSON,
	); err != nil {
		return WorkflowRetryTarget{}, workflowRetryQueryFailed()
	}
	if sourceSizeBytes.Valid {
		target.SourceSizeBytes = sourceSizeBytes.Int64
	}
	if err := json.Unmarshal([]byte(segmentsJSON), &target.Segments); err != nil {
		return WorkflowRetryTarget{}, workflowRetryQueryFailed()
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
		"status":           "retry_requested",
		"workflow_type":    strings.TrimSpace(input.WorkflowType),
		"request_id":       strings.TrimSpace(input.RequestID),
		"actor_user_id":    strings.TrimSpace(input.ActorUserID),
		"upload_id":        strings.TrimSpace(input.UploadID),
		"source_file_id":   strings.TrimSpace(input.SourceFileID),
		"retry_from_stage": strings.TrimSpace(input.ResumeStage),
	})
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "workflow retry payload must be JSON serializable"}
	}
	query := `WITH source_update AS (
  UPDATE source_files
  SET parse_status = CASE WHEN $9 = 'sequential_reading' THEN parse_status ELSE 'parsing' END,
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
    progress = CASE WHEN $9 = 'sequential_reading' THEN 24 ELSE 0 END,
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
		strings.TrimSpace(input.ResumeStage),
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
	payload := map[string]any{
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
	if retryFromStage(target) == "sequential_reading" {
		payload["retry_from_stage"] = "sequential_reading"
		segments := make([]map[string]any, 0, len(target.Segments))
		for _, segment := range target.Segments {
			segments = append(segments, map[string]any{
				"segment_id": segment.SegmentID, "segment_order": segment.SegmentOrder,
				"object_key": segment.ObjectKey, "chapter_guess": segment.ChapterGuess,
				"title_guess": segment.TitleGuess,
			})
		}
		payload["segments"] = segments
	}
	return payload
}

func retryFromStage(target WorkflowRetryTarget) string {
	if strings.TrimSpace(target.FailedStage) == "sequential_reading" && len(target.Segments) > 0 {
		return "sequential_reading"
	}
	return ""
}

func seedSegmentRetryTemporalPayload(
	input RetrySeedSegmentsInput,
	tenantID string,
	projectID string,
	runID string,
	segmentIDs []string,
	traceID string,
) map[string]any {
	actorUserID := strings.TrimSpace(input.ActorUserID)
	requestID := strings.TrimSpace(input.RequestID)
	permissions := map[string][]string{"seed_pipeline": {"run"}}
	return map[string]any{
		"context": map[string]any{
			"tenant_id":     tenantID,
			"project_id":    projectID,
			"run_id":        runID,
			"workflow_type": SeedWorkflowType,
			"actor_user_id": actorUserID,
			"trace_id":      traceID,
			"permissions":   permissions,
		},
		"tenant_id":     tenantID,
		"project_id":    projectID,
		"run_id":        runID,
		"workflow_type": SeedWorkflowType,
		"actor_user_id": actorUserID,
		"request_id":    requestID,
		"trace_id":      traceID,
		"segment_ids":   append([]string(nil), segmentIDs...),
		"permissions":   permissions,
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

func normalizeSeedSegmentRetryIDs(values []string) []string {
	seen := map[string]bool{}
	normalized := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		normalized = append(normalized, value)
	}
	return normalized
}

func validSeedSegmentRetryContext(tenantID string, projectID string, runID string, actorUserID string, segmentIDs []string) bool {
	if !isSeedUUID(tenantID) || !isSeedUUID(projectID) || !isSeedUUID(runID) || !isOptionalSeedUUID(actorUserID) || len(segmentIDs) == 0 {
		return false
	}
	for _, segmentID := range segmentIDs {
		if !isSeedUUID(segmentID) {
			return false
		}
	}
	return true
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

func seedSegmentRetryFailed() *AppError {
	return &AppError{Code: "SEED_SEGMENT_RETRY_FAILED", Message: "seed segment retry failed"}
}
