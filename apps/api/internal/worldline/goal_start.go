package worldline

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.temporal.io/sdk/client"
)

const (
	WorldlineGoalStartWorkflowType = "worldline_goal_start"
	WorldlineCastPlannerModuleKey  = "worldline_cast_planner"
	PiWorldlineGoalStartWorkflow   = "PiWorldlineGoalStartWorkflow"
	WorldlineCastTaskQueue         = "worldline-cast-streaming"
)

type StartGoalStartInput struct {
	TenantID     string
	ProjectID    string
	ActorUserID  string
	RequestID    string
	Goal         string
	AnchorPathID string
	Options      map[string]any
}

type GetGoalStartInput struct {
	TenantID string
	RunID    string
}

type ListGoalStartsInput struct {
	TenantID  string
	ProjectID string
}

type GoalStartRecord struct {
	RunID        string                   `json:"run_id"`
	TraceID      string                   `json:"trace_id,omitempty"`
	ProjectID    string                   `json:"project_id"`
	WorkflowType string                   `json:"workflow_type"`
	Status       string                   `json:"status"`
	Goal         string                   `json:"goal,omitempty"`
	AnchorPathID string                   `json:"anchor_path_id,omitempty"`
	AgentRefs    []PreparationAgentRef    `json:"agent_refs,omitempty"`
	SourceRefs   []PreparationSourceRef   `json:"source_refs,omitempty"`
	Rationale    string                   `json:"rationale,omitempty"`
	PrepareID    string                   `json:"prepare_id,omitempty"`
	SessionID    string                   `json:"session_id,omitempty"`
	ErrorCode    string                   `json:"error_code,omitempty"`
	ErrorMessage string                   `json:"error_message,omitempty"`
	CreatedAt    string                   `json:"created_at,omitempty"`
	UpdatedAt    string                   `json:"updated_at,omitempty"`
	Result       map[string]any           `json:"result,omitempty"`
}

type GoalStartStarter interface {
	StartGoalStart(context.Context, StartGoalStartInput) (GoalStartRecord, error)
}

type GoalStartReader interface {
	GetGoalStart(context.Context, GetGoalStartInput) (GoalStartRecord, error)
	ListGoalStarts(context.Context, ListGoalStartsInput) ([]GoalStartRecord, error)
}

type GoalStartAdmission struct {
	Record             GoalStartRecord
	EventID            string
	TemporalWorkflowID string
	TraceID            string
}

type GoalStartAdmissionStore interface {
	AdmitGoalStart(context.Context, StartGoalStartInput, GoalStartAdmission) (GoalStartRecord, bool, error)
	CompensateGoalStartStart(context.Context, StartGoalStartInput, GoalStartRecord, string) error
}

type DisabledGoalStartStarter struct{}

func NewDisabledGoalStartStarter() *DisabledGoalStartStarter {
	return &DisabledGoalStartStarter{}
}

func (s *DisabledGoalStartStarter) StartGoalStart(context.Context, StartGoalStartInput) (GoalStartRecord, error) {
	return GoalStartRecord{}, &AppError{
		Code:    "WORLDLINE_GOAL_START_BACKEND_UNCONFIGURED",
		Message: "worldline goal-start backend is not configured",
	}
}

type DisabledGoalStartReader struct{}

func NewDisabledGoalStartReader() *DisabledGoalStartReader {
	return &DisabledGoalStartReader{}
}

func (s *DisabledGoalStartReader) GetGoalStart(context.Context, GetGoalStartInput) (GoalStartRecord, error) {
	return GoalStartRecord{}, &AppError{
		Code:    "WORLDLINE_GOAL_START_BACKEND_UNCONFIGURED",
		Message: "worldline goal-start backend is not configured",
	}
}

func (s *DisabledGoalStartReader) ListGoalStarts(context.Context, ListGoalStartsInput) ([]GoalStartRecord, error) {
	return nil, &AppError{
		Code:    "WORLDLINE_GOAL_START_BACKEND_UNCONFIGURED",
		Message: "worldline goal-start backend is not configured",
	}
}

type SQLGoalStartAdmissionStore struct {
	db *sql.DB
}

func NewSQLGoalStartAdmissionStore(db *sql.DB) *SQLGoalStartAdmissionStore {
	return &SQLGoalStartAdmissionStore{db: db}
}

func (s *SQLGoalStartAdmissionStore) AdmitGoalStart(
	ctx context.Context,
	input StartGoalStartInput,
	admission GoalStartAdmission,
) (GoalStartRecord, bool, error) {
	if s == nil || s.db == nil {
		return GoalStartRecord{}, false, goalStartAdmissionFailed()
	}
	payload, err := goalStartQueuedEventPayload(input, admission)
	if err != nil {
		return GoalStartRecord{}, false, err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return GoalStartRecord{}, false, goalStartAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
		input.TenantID, input.ActorUserID); err != nil {
		return GoalStartRecord{}, false, goalStartAdmissionFailed()
	}
	if err := lockGoalStartProject(ctx, tx, input); err != nil {
		return GoalStartRecord{}, false, err
	}
	if err := requireGoalStartAnchor(ctx, tx, input); err != nil {
		return GoalStartRecord{}, false, err
	}
	if existing, found, err := findGoalStartReplay(ctx, tx, input); err != nil {
		return GoalStartRecord{}, false, err
	} else if found {
		if existing.Goal != input.Goal || existing.AnchorPathID != input.AnchorPathID {
			return GoalStartRecord{}, false, &AppError{
				Code:    "IDEMPOTENCY_CONFLICT",
				Message: "request_id was already used for a different worldline goal-start",
			}
		}
		if err := tx.Commit(); err != nil {
			return GoalStartRecord{}, false, goalStartAdmissionFailed()
		}
		return existing, true, nil
	}
	if err := persistGoalStartAdmission(ctx, tx, input, admission, payload); err != nil {
		return GoalStartRecord{}, false, err
	}
	if err := tx.Commit(); err != nil {
		return GoalStartRecord{}, false, goalStartAdmissionFailed()
	}
	return admission.Record, false, nil
}

func lockGoalStartProject(ctx context.Context, tx *sql.Tx, input StartGoalStartInput) error {
	var projectID string
	err := tx.QueryRowContext(ctx, `SELECT project_id::text
FROM projects
WHERE tenant_id::text = $1 AND project_id::text = $2 AND status = 'active'
FOR UPDATE`, input.TenantID, input.ProjectID).Scan(&projectID)
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "NOT_FOUND", Message: "project not found"}
	}
	if err != nil {
		return goalStartAdmissionFailed()
	}
	return nil
}

func requireGoalStartAnchor(ctx context.Context, tx *sql.Tx, input StartGoalStartInput) error {
	if input.AnchorPathID == "" {
		return nil
	}
	var found int
	err := tx.QueryRowContext(ctx, `SELECT 1
FROM worldline_saved_paths
WHERE tenant_id::text = $1 AND project_id::text = $2 AND path_id::text = $3
LIMIT 1`, input.TenantID, input.ProjectID, input.AnchorPathID).Scan(&found)
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "NOT_FOUND", Message: "worldline goal-start anchor path not found"}
	}
	if err != nil {
		return goalStartAdmissionFailed()
	}
	return nil
}

func findGoalStartReplay(
	ctx context.Context,
	tx *sql.Tx,
	input StartGoalStartInput,
) (GoalStartRecord, bool, error) {
	requestID := strings.TrimSpace(input.RequestID)
	if requestID == "" {
		return GoalStartRecord{}, false, nil
	}
	var record GoalStartRecord
	var agentRefsJSON, sourceRefsJSON, resultJSON []byte
	err := tx.QueryRowContext(ctx, `
SELECT goal_start.run_id::text,
  COALESCE(queued.payload_jsonb->>'trace_id', ''),
  goal_start.project_id::text,
  goal_start.status,
  goal_start.goal,
  COALESCE(goal_start.anchor_path_id::text, ''),
  goal_start.agent_refs_jsonb,
  goal_start.source_refs_jsonb,
  goal_start.rationale,
  COALESCE(goal_start.prepare_id::text, ''),
  COALESCE(goal_start.session_id::text, ''),
  COALESCE(goal_start.error_code, ''),
  COALESCE(goal_start.error_message, ''),
  goal_start.created_at::text,
  goal_start.updated_at::text,
  goal_start.result_jsonb
FROM worldline_goal_starts AS goal_start
JOIN workflow_runs AS workflow
  ON workflow.tenant_id = goal_start.tenant_id
 AND workflow.run_id = goal_start.workflow_run_id
JOIN workflow_events AS queued
  ON queued.tenant_id = workflow.tenant_id
 AND queued.run_id = workflow.run_id
 AND queued.event_type = 'workflow.queued'
WHERE goal_start.tenant_id = $1::uuid
  AND goal_start.project_id = $2::uuid
  AND workflow.workflow_type = $3
  AND queued.payload_jsonb->>'request_id' = $4
ORDER BY goal_start.created_at ASC
LIMIT 1`,
		input.TenantID,
		input.ProjectID,
		WorldlineGoalStartWorkflowType,
		requestID,
	).Scan(
		&record.RunID,
		&record.TraceID,
		&record.ProjectID,
		&record.Status,
		&record.Goal,
		&record.AnchorPathID,
		&agentRefsJSON,
		&sourceRefsJSON,
		&record.Rationale,
		&record.PrepareID,
		&record.SessionID,
		&record.ErrorCode,
		&record.ErrorMessage,
		&record.CreatedAt,
		&record.UpdatedAt,
		&resultJSON,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return GoalStartRecord{}, false, nil
	}
	if err != nil {
		return GoalStartRecord{}, false, goalStartAdmissionFailed()
	}
	record.WorkflowType = WorldlineGoalStartWorkflowType
	record.AgentRefs = decodePreparationAgentRefs(agentRefsJSON)
	record.SourceRefs = decodePreparationSourceRefs(sourceRefsJSON)
	record.Result = decodeJSONObject(resultJSON)
	return record, true, nil
}

func persistGoalStartAdmission(
	ctx context.Context,
	tx *sql.Tx,
	input StartGoalStartInput,
	admission GoalStartAdmission,
	payload string,
) error {
	optionsJSON, err := json.Marshal(sanitizeWorldlineOptions(input.Options))
	if err != nil {
		return &AppError{Code: "VALIDATION_FAILED", Message: "worldline goal-start options must be JSON serializable"}
	}
	result, err := tx.ExecContext(ctx, `WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  )
  VALUES (
    $1::uuid, $3::uuid, 'worldline_goal_start', $2::uuid, 'queued', 0,
    'queued', NULLIF($6, '')::uuid, $7
  )
  RETURNING tenant_id, run_id, project_id
), goal_start_insert AS (
  INSERT INTO worldline_goal_starts (
    tenant_id, run_id, workflow_run_id, project_id, status, module_key,
    goal, anchor_path_id, options_jsonb, created_by
  )
  SELECT
    workflow_insert.tenant_id, workflow_insert.run_id, workflow_insert.run_id,
    workflow_insert.project_id, 'queued', $8, $4,
    NULLIF($5, '')::uuid, $9::jsonb, NULLIF($6, '')::uuid
  FROM workflow_insert
  RETURNING tenant_id, run_id, project_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type,
  sequence, payload_jsonb
)
SELECT
  goal_start_insert.tenant_id, $10::uuid, goal_start_insert.run_id,
  'worldline_goal_start', goal_start_insert.project_id, 'workflow.queued',
  1, $11::jsonb
FROM goal_start_insert`,
		input.TenantID,
		input.ProjectID,
		admission.Record.RunID,
		input.Goal,
		input.AnchorPathID,
		input.ActorUserID,
		admission.TemporalWorkflowID,
		WorldlineCastPlannerModuleKey,
		string(optionsJSON),
		admission.EventID,
		payload,
	)
	if err != nil {
		return goalStartAdmissionFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil || affected != 1 {
		return goalStartAdmissionFailed()
	}
	return nil
}

func (s *SQLGoalStartAdmissionStore) CompensateGoalStartStart(
	ctx context.Context,
	input StartGoalStartInput,
	record GoalStartRecord,
	eventID string,
) error {
	if s == nil || s.db == nil {
		return goalStartCompensationFailed()
	}
	payload, err := json.Marshal(map[string]any{
		"status":        "failed",
		"workflow_type": WorldlineGoalStartWorkflowType,
		"request_id":    input.RequestID,
		"run_id":        record.RunID,
		"error_code":    "WORKFLOW_FAILED",
	})
	if err != nil {
		return goalStartCompensationFailed()
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return goalStartCompensationFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
		input.TenantID, input.ActorUserID); err != nil {
		return goalStartCompensationFailed()
	}
	result, err := tx.ExecContext(ctx, `WITH failed_run AS (
  UPDATE workflow_runs
  SET status = 'failed', progress = 100, message = 'failed to start',
      error_code = 'WORKFLOW_FAILED',
      error_message = 'failed to start worldline goal-start workflow',
      updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND run_id::text = $3
    AND workflow_type = 'worldline_goal_start' AND status = 'queued'
  RETURNING tenant_id, run_id, project_id
), failed_goal AS (
  UPDATE worldline_goal_starts
  SET status = 'failed',
      error_code = 'WORKFLOW_FAILED',
      error_message = 'failed to start worldline goal-start workflow',
      updated_at = now()
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND run_id::text = $3
    AND status = 'queued'
    AND EXISTS (SELECT 1 FROM failed_run)
  RETURNING tenant_id, run_id, project_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type,
  sequence, payload_jsonb
)
SELECT tenant_id, $4::uuid, run_id, 'worldline_goal_start', project_id,
       'workflow.start_failed', 2, $5::jsonb
FROM failed_goal`,
		input.TenantID,
		input.ProjectID,
		record.RunID,
		eventID,
		string(payload),
	)
	if err != nil {
		return goalStartCompensationFailed()
	}
	affected, err := result.RowsAffected()
	if err != nil || affected != 1 {
		return goalStartCompensationFailed()
	}
	if err := tx.Commit(); err != nil {
		return goalStartCompensationFailed()
	}
	return nil
}

type SQLGoalStartStarterConfig struct {
	Store     GoalStartAdmissionStore
	NewID     func() string
	Client    TemporalWorkflowClient
	TaskQueue string
}

type SQLGoalStartStarter struct {
	store     GoalStartAdmissionStore
	newID     func() string
	client    TemporalWorkflowClient
	taskQueue string
}

func NewSQLGoalStartStarter(config SQLGoalStartStarterConfig) *SQLGoalStartStarter {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	taskQueue := strings.TrimSpace(config.TaskQueue)
	if taskQueue == "" {
		taskQueue = WorldlineCastTaskQueue
	}
	return &SQLGoalStartStarter{
		store:     config.Store,
		newID:     newID,
		client:    config.Client,
		taskQueue: taskQueue,
	}
}

func (s *SQLGoalStartStarter) StartGoalStart(ctx context.Context, input StartGoalStartInput) (GoalStartRecord, error) {
	input = normalizeGoalStartInput(input)
	if err := validateGoalStartInput(input); err != nil {
		return GoalStartRecord{}, err
	}
	if s == nil || s.store == nil || s.client == nil {
		return GoalStartRecord{}, &AppError{
			Code:    "WORLDLINE_GOAL_START_BACKEND_UNCONFIGURED",
			Message: "worldline goal-start backend is not configured",
		}
	}
	admission := s.newGoalStartAdmission(input)
	record, replayed, err := s.store.AdmitGoalStart(ctx, input, admission)
	if err != nil {
		return GoalStartRecord{}, sanitizeGoalStartAdmissionError(err)
	}
	if replayed {
		return record, nil
	}
	if err := s.startTemporalWorkflow(ctx, input, record, admission); err != nil {
		return GoalStartRecord{}, err
	}
	return record, nil
}

func (s *SQLGoalStartStarter) newGoalStartAdmission(input StartGoalStartInput) GoalStartAdmission {
	runID := s.newID()
	return GoalStartAdmission{
		Record: GoalStartRecord{
			RunID:        runID,
			TraceID:      "trace_" + runID,
			ProjectID:    input.ProjectID,
			WorkflowType: WorldlineGoalStartWorkflowType,
			Status:       "queued",
			Goal:         input.Goal,
			AnchorPathID: input.AnchorPathID,
		},
		EventID:            s.newID(),
		TemporalWorkflowID: "worldline_goal_start_" + runID,
		TraceID:            "trace_" + runID,
	}
}

func (s *SQLGoalStartStarter) startTemporalWorkflow(
	ctx context.Context,
	input StartGoalStartInput,
	record GoalStartRecord,
	admission GoalStartAdmission,
) error {
	_, err := s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:                       admission.TemporalWorkflowID,
		TaskQueue:                s.taskQueue,
		WorkflowExecutionTimeout: 12 * time.Hour,
		WorkflowRunTimeout:       12 * time.Hour,
	}, PiWorldlineGoalStartWorkflow, goalStartTemporalPayload(input, record, admission.TraceID))
	if err == nil {
		return nil
	}
	compensationContext, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
	defer cancel()
	if compensationErr := s.store.CompensateGoalStartStart(
		compensationContext,
		input,
		record,
		s.newID(),
	); compensationErr != nil {
		return goalStartCompensationFailed()
	}
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to start worldline goal-start workflow"}
}

type SQLGoalStartReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLGoalStartReader struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLGoalStartReader(config SQLGoalStartReaderConfig) *SQLGoalStartReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 50
	}
	return &SQLGoalStartReader{queryer: config.Queryer, limit: limit}
}

func (s *SQLGoalStartReader) GetGoalStart(ctx context.Context, input GetGoalStartInput) (GoalStartRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	runID := strings.TrimSpace(input.RunID)
	if tenantID == "" || runID == "" {
		return GoalStartRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if s == nil || s.queryer == nil {
		return GoalStartRecord{}, &AppError{
			Code:    "WORLDLINE_GOAL_START_BACKEND_UNCONFIGURED",
			Message: "worldline goal-start backend is not configured",
		}
	}
	query := goalStartRecordSelectQuery() + `
WHERE tenant_id::text = $1 AND run_id::text = $2
LIMIT 1`
	rows, err := queryWorldlineTenantSQL(ctx, s.queryer, tenantID, query, tenantID, runID)
	if err != nil {
		return GoalStartRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		return GoalStartRecord{}, &AppError{Code: "NOT_FOUND", Message: "worldline goal-start not found"}
	}
	record, err := scanGoalStartRecord(rows)
	if err != nil {
		return GoalStartRecord{}, err
	}
	return record, nil
}

func (s *SQLGoalStartReader) ListGoalStarts(ctx context.Context, input ListGoalStartsInput) ([]GoalStartRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	if tenantID == "" || projectID == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if s == nil || s.queryer == nil {
		return nil, &AppError{
			Code:    "WORLDLINE_GOAL_START_BACKEND_UNCONFIGURED",
			Message: "worldline goal-start backend is not configured",
		}
	}
	query := goalStartRecordSelectQuery() + `
WHERE tenant_id::text = $1 AND project_id::text = $2
ORDER BY created_at DESC
LIMIT $3`
	rows, err := queryWorldlineTenantSQL(ctx, s.queryer, tenantID, query, tenantID, projectID, s.limit)
	if err != nil {
		return nil, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	records := []GoalStartRecord{}
	for rows.Next() {
		record, err := scanGoalStartRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	return records, nil
}

func goalStartRecordSelectQuery() string {
	return `SELECT
  run_id::text,
  project_id::text,
  status,
  goal,
  COALESCE(anchor_path_id::text, ''),
  agent_refs_jsonb,
  source_refs_jsonb,
  rationale,
  COALESCE(prepare_id::text, ''),
  COALESCE(session_id::text, ''),
  COALESCE(error_code, ''),
  COALESCE(error_message, ''),
  created_at::text,
  updated_at::text,
  result_jsonb
FROM worldline_goal_starts`
}

func scanGoalStartRecord(rows interface {
	Scan(dest ...any) error
}) (GoalStartRecord, error) {
	var record GoalStartRecord
	var agentRefsJSON, sourceRefsJSON, resultJSON []byte
	if err := rows.Scan(
		&record.RunID,
		&record.ProjectID,
		&record.Status,
		&record.Goal,
		&record.AnchorPathID,
		&agentRefsJSON,
		&sourceRefsJSON,
		&record.Rationale,
		&record.PrepareID,
		&record.SessionID,
		&record.ErrorCode,
		&record.ErrorMessage,
		&record.CreatedAt,
		&record.UpdatedAt,
		&resultJSON,
	); err != nil {
		return GoalStartRecord{}, &AppError{Code: "WORLDLINE_QUERY_FAILED", Message: err.Error()}
	}
	record.WorkflowType = WorldlineGoalStartWorkflowType
	record.TraceID = "trace_" + record.RunID
	record.AgentRefs = decodePreparationAgentRefs(agentRefsJSON)
	record.SourceRefs = decodePreparationSourceRefs(sourceRefsJSON)
	record.Result = decodeJSONObject(resultJSON)
	return record, nil
}

func normalizeGoalStartInput(input StartGoalStartInput) StartGoalStartInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Goal = strings.TrimSpace(input.Goal)
	input.AnchorPathID = strings.TrimSpace(input.AnchorPathID)
	input.Options = sanitizeWorldlineOptions(input.Options)
	return input
}

func validateGoalStartInput(input StartGoalStartInput) error {
	if input.TenantID == "" || input.ProjectID == "" || input.ActorUserID == "" ||
		input.RequestID == "" || input.Goal == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, actor_user_id, request_id, and goal are required",
		}
	}
	if input.AnchorPathID != "" {
		if _, err := uuid.Parse(input.AnchorPathID); err != nil {
			return &AppError{Code: "VALIDATION_FAILED", Message: "worldline goal-start anchor_path_id is invalid"}
		}
	}
	return nil
}

func goalStartQueuedEventPayload(input StartGoalStartInput, admission GoalStartAdmission) (string, error) {
	payload, err := json.Marshal(map[string]any{
		"status":         "queued",
		"workflow_type":  WorldlineGoalStartWorkflowType,
		"request_id":     input.RequestID,
		"trace_id":       admission.TraceID,
		"run_id":         admission.Record.RunID,
		"anchor_path_id": input.AnchorPathID,
		"options":        sanitizeWorldlineOptions(input.Options),
	})
	if err != nil {
		return "", &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "worldline goal-start admission payload must be JSON serializable",
		}
	}
	return string(payload), nil
}

func goalStartTemporalPayload(input StartGoalStartInput, record GoalStartRecord, traceID string) map[string]any {
	return map[string]any{
		"tenant_id":      input.TenantID,
		"project_id":     record.ProjectID,
		"run_id":         record.RunID,
		"workflow_type":  WorldlineGoalStartWorkflowType,
		"requested_by":   input.ActorUserID,
		"request_id":     input.RequestID,
		"trace_id":       traceID,
		"goal":           input.Goal,
		"anchor_path_id": input.AnchorPathID,
		"options": map[string]any{
			"module_key":           WorldlineCastPlannerModuleKey,
			"required_module_keys": []string{WorldlineCastPlannerModuleKey},
		},
	}
}

func sanitizeGoalStartAdmissionError(err error) error {
	var appErr *AppError
	if !errors.As(err, &appErr) {
		return goalStartAdmissionFailed()
	}
	switch appErr.Code {
	case "VALIDATION_FAILED", "IDEMPOTENCY_CONFLICT", "NOT_FOUND":
		return &AppError{Code: appErr.Code, Message: appErr.Message}
	default:
		return goalStartAdmissionFailed()
	}
}

func goalStartAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "worldline goal-start admission failed"}
}

func goalStartCompensationFailed() *AppError {
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to record worldline goal-start start failure"}
}

func decodePreparationAgentRefs(raw []byte) []PreparationAgentRef {
	if len(raw) == 0 {
		return nil
	}
	var items []PreparationAgentRef
	if err := json.Unmarshal(raw, &items); err != nil {
		return nil
	}
	return normalizePreparationAgentRefs(items)
}

func decodePreparationSourceRefs(raw []byte) []PreparationSourceRef {
	if len(raw) == 0 {
		return nil
	}
	var items []PreparationSourceRef
	if err := json.Unmarshal(raw, &items); err != nil {
		return nil
	}
	return normalizePreparationSourceRefs(items)
}

func decodeJSONObject(raw []byte) map[string]any {
	if len(raw) == 0 {
		return map[string]any{}
	}
	var value map[string]any
	if err := json.Unmarshal(raw, &value); err != nil || value == nil {
		return map[string]any{}
	}
	return value
}
