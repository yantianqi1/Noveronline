package worldline

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"go.temporal.io/sdk/client"
)

const (
	WorldlineAutoEvolutionWorkflowType = "worldline_auto_evolution"
	WorldlineAutoEvolutionModuleKey    = "worldline_director"
	WorldlineAutoEvolutionWorldScope   = "current_world"
	worldlineAutoEvolutionWorkflow     = "WorldlineAutoEvolutionWorkflow"
)

type StartAutoEvolutionInput struct {
	TenantID    string
	ProjectID   string
	SessionID   string
	ActorUserID string
	RequestID   string
	MaxSteps    int
	Options     map[string]any
}

type AutoEvolutionRun struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	SessionID    string `json:"session_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
	MaxSteps     int    `json:"max_steps"`
}

type AutoEvolutionStarter interface {
	StartAutoEvolution(context.Context, StartAutoEvolutionInput) (AutoEvolutionRun, error)
}

type AutoEvolutionAdmission struct {
	Run                AutoEvolutionRun
	EventID            string
	TemporalWorkflowID string
	TraceID            string
}

type AutoEvolutionAdmissionStore interface {
	AdmitAutoEvolution(context.Context, StartAutoEvolutionInput, AutoEvolutionAdmission) (AutoEvolutionRun, bool, error)
	CompensateAutoEvolutionStart(context.Context, StartAutoEvolutionInput, AutoEvolutionRun, string) error
}

type DisabledAutoEvolutionStarter struct{}

func NewDisabledAutoEvolutionStarter() *DisabledAutoEvolutionStarter {
	return &DisabledAutoEvolutionStarter{}
}

func (s *DisabledAutoEvolutionStarter) StartAutoEvolution(context.Context, StartAutoEvolutionInput) (AutoEvolutionRun, error) {
	return AutoEvolutionRun{}, &AppError{
		Code:    "WORLDLINE_AUTO_EVOLUTION_BACKEND_UNCONFIGURED",
		Message: "worldline auto-evolution backend is not configured",
	}
}

type SQLAutoEvolutionAdmissionStore struct {
	db *sql.DB
}

func NewSQLAutoEvolutionAdmissionStore(db *sql.DB) *SQLAutoEvolutionAdmissionStore {
	return &SQLAutoEvolutionAdmissionStore{db: db}
}

func (s *SQLAutoEvolutionAdmissionStore) AdmitAutoEvolution(
	ctx context.Context,
	input StartAutoEvolutionInput,
	admission AutoEvolutionAdmission,
) (AutoEvolutionRun, bool, error) {
	if s == nil || s.db == nil {
		return AutoEvolutionRun{}, false, autoEvolutionAdmissionFailed()
	}
	payload, err := autoEvolutionQueuedEventPayload(input, admission.Run, admission.TraceID)
	if err != nil {
		return AutoEvolutionRun{}, false, err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return AutoEvolutionRun{}, false, autoEvolutionAdmissionFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setAutoEvolutionTenantContext(ctx, tx, input); err != nil {
		return AutoEvolutionRun{}, false, err
	}
	if err := lockAutoEvolutionSession(ctx, tx, input); err != nil {
		return AutoEvolutionRun{}, false, err
	}
	if existing, found, err := findAutoEvolutionReplay(ctx, tx, input); err != nil {
		return AutoEvolutionRun{}, false, err
	} else if found {
		if err := tx.Commit(); err != nil {
			return AutoEvolutionRun{}, false, autoEvolutionAdmissionFailed()
		}
		return existing, true, nil
	}
	if active, err := hasActiveAutoEvolution(ctx, tx, input); err != nil {
		return AutoEvolutionRun{}, false, err
	} else if active {
		return AutoEvolutionRun{}, false, autoEvolutionActive()
	}
	if err := persistAutoEvolutionAdmission(ctx, tx, input, admission, payload); err != nil {
		return AutoEvolutionRun{}, false, err
	}
	if err := tx.Commit(); err != nil {
		return AutoEvolutionRun{}, false, autoEvolutionAdmissionFailed()
	}
	return admission.Run, false, nil
}

func setAutoEvolutionTenantContext(ctx context.Context, tx *sql.Tx, input StartAutoEvolutionInput) error {
	_, err := tx.ExecContext(
		ctx,
		"SELECT app_set_tenant_context($1::uuid, $2::uuid, false)",
		input.TenantID,
		input.ActorUserID,
	)
	if err != nil {
		return autoEvolutionAdmissionFailed()
	}
	return nil
}

func lockAutoEvolutionSession(ctx context.Context, tx *sql.Tx, input StartAutoEvolutionInput) error {
	var status, lifecycle string
	err := tx.QueryRowContext(ctx, `SELECT status, lifecycle
FROM worldline_sessions
WHERE tenant_id::text = $1 AND project_id::text = $2 AND session_id::text = $3
FOR UPDATE`, input.TenantID, input.ProjectID, input.SessionID).Scan(&status, &lifecycle)
	if errors.Is(err, sql.ErrNoRows) {
		return &AppError{Code: "NOT_FOUND", Message: "worldline session not found"}
	}
	if err != nil {
		return autoEvolutionAdmissionFailed()
	}
	if lifecycle != "active" {
		return &AppError{
			Code:    "CURRENT_WORLD_REQUIRED",
			Message: "worldline auto-evolution requires the active current_world session",
		}
	}
	if status != "queued" && status != "running" && status != "paused" {
		return &AppError{Code: "WORLDLINE_SESSION_NOT_ACTIVE", Message: "worldline session is not active"}
	}
	return nil
}

func findAutoEvolutionReplay(
	ctx context.Context,
	tx *sql.Tx,
	input StartAutoEvolutionInput,
) (AutoEvolutionRun, bool, error) {
	var run AutoEvolutionRun
	err := tx.QueryRowContext(ctx, `SELECT
  workflow_run.run_id::text,
  workflow_run.project_id::text,
  queued_event.payload_jsonb->>'session_id',
  workflow_run.workflow_type,
  workflow_run.status,
  COALESCE((queued_event.payload_jsonb->>'max_steps')::bigint, 0)
FROM workflow_runs AS workflow_run
JOIN workflow_events AS queued_event
  ON queued_event.tenant_id = workflow_run.tenant_id
 AND queued_event.run_id = workflow_run.run_id
 AND queued_event.workflow_type = workflow_run.workflow_type
WHERE workflow_run.tenant_id::text = $1
  AND workflow_run.project_id::text = $2
  AND workflow_run.started_by::text = $4
  AND workflow_run.workflow_type = 'worldline_auto_evolution'
  AND queued_event.event_type = 'workflow.queued'
  AND queued_event.payload_jsonb->>'session_id' = $3
  AND queued_event.payload_jsonb->>'request_id' = $5
  AND queued_event.payload_jsonb->>'world_scope' = 'current_world'
ORDER BY queued_event.created_at ASC
LIMIT 1`, input.TenantID, input.ProjectID, input.SessionID, input.ActorUserID, input.RequestID).Scan(
		&run.RunID,
		&run.ProjectID,
		&run.SessionID,
		&run.WorkflowType,
		&run.Status,
		&run.MaxSteps,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return AutoEvolutionRun{}, false, nil
	}
	if err != nil {
		return AutoEvolutionRun{}, false, autoEvolutionAdmissionFailed()
	}
	return run, true, nil
}

func hasActiveAutoEvolution(ctx context.Context, tx *sql.Tx, input StartAutoEvolutionInput) (bool, error) {
	var active bool
	err := tx.QueryRowContext(ctx, `SELECT EXISTS (
  SELECT 1
  FROM workflow_runs AS workflow_run
  JOIN workflow_events AS queued_event
    ON queued_event.tenant_id = workflow_run.tenant_id
   AND queued_event.run_id = workflow_run.run_id
   AND queued_event.workflow_type = workflow_run.workflow_type
  WHERE workflow_run.tenant_id::text = $1
    AND workflow_run.project_id::text = $2
    AND workflow_run.workflow_type = 'worldline_auto_evolution'
    AND workflow_run.status IN ('queued', 'running')
    AND queued_event.event_type = 'workflow.queued'
    AND queued_event.payload_jsonb->>'session_id' = $3
    AND queued_event.payload_jsonb->>'world_scope' = 'current_world'
)`, input.TenantID, input.ProjectID, input.SessionID).Scan(&active)
	if err != nil {
		return false, autoEvolutionAdmissionFailed()
	}
	return active, nil
}

func persistAutoEvolutionAdmission(
	ctx context.Context,
	tx *sql.Tx,
	input StartAutoEvolutionInput,
	admission AutoEvolutionAdmission,
	payload string,
) error {
	result, err := tx.ExecContext(ctx, autoEvolutionAdmissionQuery(),
		input.TenantID,
		input.ProjectID,
		input.SessionID,
		admission.Run.RunID,
		input.ActorUserID,
		admission.TemporalWorkflowID,
		admission.EventID,
		payload,
	)
	if err != nil {
		return autoEvolutionAdmissionFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return autoEvolutionAdmissionFailed()
	}
	return nil
}

func autoEvolutionAdmissionQuery() string {
	return `WITH session_scope AS (
  SELECT tenant_id, project_id, session_id
  FROM worldline_sessions
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND session_id::text = $3
    AND lifecycle = 'active'
    AND status IN ('queued', 'running', 'paused')
),
workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  )
  SELECT tenant_id, $4::uuid, 'worldline_auto_evolution', project_id,
         'queued', 0, 'queued', $5::uuid, $6
  FROM session_scope
  RETURNING tenant_id, run_id, project_id
),
event_insert AS (
  INSERT INTO workflow_events (
    tenant_id, event_id, run_id, workflow_type, project_id,
    event_type, sequence, payload_jsonb
  )
  SELECT tenant_id, $7::uuid, run_id, 'worldline_auto_evolution', project_id,
         'workflow.queued', 1, $8::jsonb
  FROM workflow_insert
  RETURNING 1
),
session_update AS (
  UPDATE worldline_sessions
  SET status = 'running', updated_at = now()
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND session_id::text = $3
    AND lifecycle = 'active'
    AND status IN ('queued', 'running', 'paused')
    AND EXISTS (SELECT 1 FROM event_insert)
  RETURNING 1
)
SELECT 1 FROM event_insert JOIN session_update ON true`
}

func (s *SQLAutoEvolutionAdmissionStore) CompensateAutoEvolutionStart(
	ctx context.Context,
	input StartAutoEvolutionInput,
	run AutoEvolutionRun,
	failureEventID string,
) error {
	if s == nil || s.db == nil {
		return autoEvolutionCompensationFailed()
	}
	payload, err := autoEvolutionStartFailurePayload(input, run)
	if err != nil {
		return autoEvolutionCompensationFailed()
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return autoEvolutionCompensationFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setAutoEvolutionTenantContext(ctx, tx, input); err != nil {
		return autoEvolutionCompensationFailed()
	}
	result, err := tx.ExecContext(ctx, autoEvolutionCompensationQuery(),
		input.TenantID,
		input.ProjectID,
		run.RunID,
		input.ActorUserID,
		input.SessionID,
		failureEventID,
		payload,
	)
	if err != nil {
		return autoEvolutionCompensationFailed()
	}
	if affected, rowsErr := result.RowsAffected(); rowsErr != nil || affected != 1 {
		return autoEvolutionCompensationFailed()
	}
	if err := tx.Commit(); err != nil {
		return autoEvolutionCompensationFailed()
	}
	return nil
}

func autoEvolutionCompensationQuery() string {
	return `WITH session_lock AS (
  SELECT session_id
  FROM worldline_sessions
  WHERE tenant_id::text = $1 AND project_id::text = $2 AND session_id::text = $5
  FOR UPDATE
),
failed_run AS (
  UPDATE workflow_runs
  SET status = 'failed', progress = 100, message = 'failed to start',
      error_code = 'WORKFLOW_FAILED',
      error_message = 'failed to start worldline auto-evolution workflow',
      updated_at = now()
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND run_id::text = $3
    AND started_by::text = $4
    AND workflow_type = 'worldline_auto_evolution'
    AND status = 'queued'
    AND EXISTS (SELECT 1 FROM session_lock)
  RETURNING tenant_id, run_id, project_id
),
event_insert AS (
  INSERT INTO workflow_events (
    tenant_id, event_id, run_id, workflow_type, project_id,
    event_type, sequence, payload_jsonb
  )
  SELECT tenant_id, $6::uuid, run_id, 'worldline_auto_evolution', project_id,
         'workflow.start_failed',
         (SELECT COALESCE(MAX(sequence), 0) + 1
            FROM workflow_events
           WHERE tenant_id = failed_run.tenant_id AND run_id = failed_run.run_id),
         $7::jsonb
  FROM failed_run
  RETURNING 1
),
session_update AS (
  UPDATE worldline_sessions
  SET status = CASE
        WHEN EXISTS (
          SELECT 1
          FROM workflow_runs AS active_run
          JOIN workflow_events AS queued_event
            ON queued_event.tenant_id = active_run.tenant_id
           AND queued_event.run_id = active_run.run_id
           AND queued_event.workflow_type = active_run.workflow_type
          WHERE active_run.tenant_id::text = $1
            AND active_run.project_id::text = $2
            AND active_run.run_id::text <> $3
            AND active_run.workflow_type = 'worldline_auto_evolution'
            AND active_run.status IN ('queued', 'running')
            AND queued_event.event_type = 'workflow.queued'
            AND queued_event.payload_jsonb->>'session_id' = $5
            AND queued_event.payload_jsonb->>'world_scope' = 'current_world'
        ) THEN status ELSE 'paused' END,
      updated_at = now()
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND session_id::text = $5
    AND EXISTS (SELECT 1 FROM event_insert)
  RETURNING 1
)
SELECT 1 FROM event_insert JOIN session_update ON true`
}

type SQLAutoEvolutionStarterConfig struct {
	Store     AutoEvolutionAdmissionStore
	NewID     func() string
	Client    TemporalWorkflowClient
	TaskQueue string
}

type SQLAutoEvolutionStarter struct {
	store     AutoEvolutionAdmissionStore
	newID     func() string
	client    TemporalWorkflowClient
	taskQueue string
}

func NewSQLAutoEvolutionStarter(config SQLAutoEvolutionStarterConfig) *SQLAutoEvolutionStarter {
	newID := config.NewID
	if newID == nil {
		newID = newUUID
	}
	return &SQLAutoEvolutionStarter{
		store:     config.Store,
		newID:     newID,
		client:    config.Client,
		taskQueue: normalizeWorldlineTaskQueue(config.TaskQueue),
	}
}

func (s *SQLAutoEvolutionStarter) StartAutoEvolution(
	ctx context.Context,
	input StartAutoEvolutionInput,
) (AutoEvolutionRun, error) {
	input = normalizeAutoEvolutionInput(input)
	if err := validateAutoEvolutionInput(input); err != nil {
		return AutoEvolutionRun{}, err
	}
	if s == nil || s.store == nil || s.client == nil {
		return AutoEvolutionRun{}, &AppError{
			Code:    "WORLDLINE_AUTO_EVOLUTION_BACKEND_UNCONFIGURED",
			Message: "worldline auto-evolution backend is not configured",
		}
	}
	if _, err := json.Marshal(input.Options); err != nil {
		return AutoEvolutionRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "worldline auto-evolution options must be JSON serializable",
		}
	}
	admission := s.newAutoEvolutionAdmission(input)
	run, replayed, err := s.store.AdmitAutoEvolution(ctx, input, admission)
	if err != nil {
		return AutoEvolutionRun{}, sanitizeAutoEvolutionAdmissionError(err)
	}
	if replayed {
		return run, nil
	}
	if err := s.startTemporalWorkflow(ctx, input, run, admission); err != nil {
		return AutoEvolutionRun{}, err
	}
	return run, nil
}

func (s *SQLAutoEvolutionStarter) newAutoEvolutionAdmission(input StartAutoEvolutionInput) AutoEvolutionAdmission {
	runID := s.newID()
	return AutoEvolutionAdmission{
		Run: AutoEvolutionRun{
			RunID:        runID,
			ProjectID:    input.ProjectID,
			SessionID:    input.SessionID,
			WorkflowType: WorldlineAutoEvolutionWorkflowType,
			Status:       "queued",
			MaxSteps:     input.MaxSteps,
		},
		EventID:            s.newID(),
		TemporalWorkflowID: "worldline_auto_evolution_" + runID,
		TraceID:            "trace_" + runID,
	}
}

func (s *SQLAutoEvolutionStarter) startTemporalWorkflow(
	ctx context.Context,
	input StartAutoEvolutionInput,
	run AutoEvolutionRun,
	admission AutoEvolutionAdmission,
) error {
	_, err := s.client.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
		ID:        admission.TemporalWorkflowID,
		TaskQueue: s.taskQueue,
	}, worldlineAutoEvolutionWorkflow, autoEvolutionTemporalPayload(input, run, admission.TraceID))
	if err == nil {
		return nil
	}
	compensationContext, cancel := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Second)
	defer cancel()
	if compensationErr := s.store.CompensateAutoEvolutionStart(
		compensationContext,
		input,
		run,
		s.newID(),
	); compensationErr != nil {
		return autoEvolutionCompensationFailed()
	}
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to start worldline auto-evolution workflow"}
}

func normalizeAutoEvolutionInput(input StartAutoEvolutionInput) StartAutoEvolutionInput {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.SessionID = strings.TrimSpace(input.SessionID)
	input.ActorUserID = strings.TrimSpace(input.ActorUserID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Options = sanitizeAutoEvolutionOptions(input.Options)
	return input
}

func validateAutoEvolutionInput(input StartAutoEvolutionInput) error {
	if input.TenantID == "" || input.ProjectID == "" || input.SessionID == "" ||
		input.ActorUserID == "" || input.RequestID == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, session_id, actor_user_id, and request_id are required",
		}
	}
	if input.MaxSteps < 1 {
		return &AppError{Code: "VALIDATION_FAILED", Message: "max_steps must be greater than zero"}
	}
	return nil
}

func sanitizeAutoEvolutionOptions(options map[string]any) map[string]any {
	sanitized := make(map[string]any)
	for key, value := range options {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if normalizedKey == "" || autoEvolutionOptionKeyForbidden(normalizedKey) {
			continue
		}
		sanitized[key] = sanitizeAutoEvolutionOptionValue(value)
	}
	return sanitized
}

func sanitizeAutoEvolutionOptionValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeAutoEvolutionOptions(typed)
	case []any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, sanitizeAutoEvolutionOptionValue(item))
		}
		return items
	case []map[string]any:
		items := make([]map[string]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, sanitizeAutoEvolutionOptions(item))
		}
		return items
	default:
		return value
	}
}

func autoEvolutionOptionKeyForbidden(key string) bool {
	if worldlineOptionKeySensitive(key) {
		return true
	}
	switch key {
	case "branch", "branch_id", "branch_ids", "branches", "comparison", "comparisons", "world_scope", "worlds":
		return true
	default:
		return false
	}
}

func autoEvolutionQueuedEventPayload(
	input StartAutoEvolutionInput,
	run AutoEvolutionRun,
	traceID string,
) (string, error) {
	payload, err := json.Marshal(map[string]any{
		"status":        "queued",
		"workflow_type": WorldlineAutoEvolutionWorkflowType,
		"request_id":    input.RequestID,
		"trace_id":      traceID,
		"session_id":    input.SessionID,
		"max_steps":     run.MaxSteps,
		"world_scope":   WorldlineAutoEvolutionWorldScope,
	})
	if err != nil {
		return "", &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "worldline auto-evolution admission payload must be JSON serializable",
		}
	}
	return string(payload), nil
}

func autoEvolutionStartFailurePayload(input StartAutoEvolutionInput, run AutoEvolutionRun) (string, error) {
	payload, err := json.Marshal(map[string]any{
		"status":        "failed",
		"workflow_type": WorldlineAutoEvolutionWorkflowType,
		"request_id":    input.RequestID,
		"session_id":    run.SessionID,
		"max_steps":     run.MaxSteps,
		"world_scope":   WorldlineAutoEvolutionWorldScope,
		"error_code":    "WORKFLOW_FAILED",
	})
	if err != nil {
		return "", autoEvolutionCompensationFailed()
	}
	return string(payload), nil
}

func autoEvolutionTemporalPayload(
	input StartAutoEvolutionInput,
	run AutoEvolutionRun,
	traceID string,
) map[string]any {
	return map[string]any{
		"context": map[string]any{
			"tenant_id": input.TenantID, "project_id": run.ProjectID, "run_id": run.RunID,
			"workflow_type": WorldlineAutoEvolutionWorkflowType, "actor_user_id": input.ActorUserID,
			"module_key": WorldlineAutoEvolutionModuleKey, "trace_id": traceID,
			"permissions": map[string][]string{WorldlineAutoEvolutionModuleKey: {"run"}},
		},
		"session_id":  run.SessionID,
		"max_steps":   run.MaxSteps,
		"world_scope": WorldlineAutoEvolutionWorldScope,
		"request_id":  input.RequestID,
		"options":     input.Options,
	}
}

func sanitizeAutoEvolutionAdmissionError(err error) error {
	var appErr *AppError
	if !errors.As(err, &appErr) {
		return autoEvolutionAdmissionFailed()
	}
	switch appErr.Code {
	case "VALIDATION_FAILED":
		return &AppError{Code: appErr.Code, Message: "worldline auto-evolution validation failed"}
	case "NOT_FOUND":
		return &AppError{Code: appErr.Code, Message: "worldline session not found"}
	case "CURRENT_WORLD_REQUIRED":
		return &AppError{Code: appErr.Code, Message: "worldline auto-evolution requires the active current_world session"}
	case "WORLDLINE_SESSION_NOT_ACTIVE":
		return &AppError{Code: appErr.Code, Message: "worldline session is not active"}
	case "WORLDLINE_AUTO_EVOLUTION_ACTIVE":
		return autoEvolutionActive()
	default:
		return autoEvolutionAdmissionFailed()
	}
}

func autoEvolutionActive() *AppError {
	return &AppError{
		Code:    "WORLDLINE_AUTO_EVOLUTION_ACTIVE",
		Message: "worldline session already has an active auto-evolution",
	}
}

func autoEvolutionAdmissionFailed() *AppError {
	return &AppError{Code: "WORKFLOW_ADMISSION_FAILED", Message: "worldline auto-evolution admission failed"}
}

func autoEvolutionCompensationFailed() *AppError {
	return &AppError{Code: "WORKFLOW_FAILED", Message: "failed to record worldline auto-evolution start failure"}
}
