package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

type CancelWorkflowRunInput struct {
	TenantID    string
	RunID       string
	ActorUserID string
	RequestID   string
}

type WorkflowRunCancellation struct {
	RunID  string
	Status string
}

type WorkflowCanceller interface {
	CancelWorkflowRun(context.Context, CancelWorkflowRunInput) (WorkflowRunCancellation, error)
}

type WorkflowCancellationTargetInput struct {
	TenantID string
	RunID    string
}

type WorkflowCancellationTarget struct {
	RunID              string
	ProjectID          string
	WorkflowType       string
	TemporalWorkflowID string
}

type WorkflowCancellationInput struct {
	TenantID     string
	ProjectID    string
	RunID        string
	WorkflowType string
	ActorUserID  string
	RequestID    string
	Status       string
}

type WorkflowCancellationStore interface {
	GetWorkflowCancellationTarget(context.Context, WorkflowCancellationTargetInput) (WorkflowCancellationTarget, error)
	CancelWorkflowRun(context.Context, WorkflowCancellationInput) error
}

type DisabledWorkflowCanceller struct{}

func NewDisabledWorkflowCanceller() *DisabledWorkflowCanceller {
	return &DisabledWorkflowCanceller{}
}

func (c *DisabledWorkflowCanceller) CancelWorkflowRun(_ context.Context, _ CancelWorkflowRunInput) (WorkflowRunCancellation, error) {
	return WorkflowRunCancellation{}, &AppError{
		Code:    "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED",
		Message: "workflow cancellation backend is not configured",
	}
}

type TemporalWorkflowCancellerConfig struct {
	Client TemporalWorkflowClient
	Store  WorkflowCancellationStore
}

type TemporalWorkflowCanceller struct {
	client TemporalWorkflowClient
	store  WorkflowCancellationStore
}

func NewTemporalWorkflowCanceller(config TemporalWorkflowCancellerConfig) *TemporalWorkflowCanceller {
	return &TemporalWorkflowCanceller{client: config.Client, store: config.Store}
}

func (c *TemporalWorkflowCanceller) CancelWorkflowRun(ctx context.Context, input CancelWorkflowRunInput) (WorkflowRunCancellation, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return WorkflowRunCancellation{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if c.client == nil || c.store == nil {
		return WorkflowRunCancellation{}, &AppError{
			Code:    "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED",
			Message: "workflow cancellation backend is not configured",
		}
	}
	target, err := c.store.GetWorkflowCancellationTarget(ctx, WorkflowCancellationTargetInput{
		TenantID: strings.TrimSpace(input.TenantID),
		RunID:    strings.TrimSpace(input.RunID),
	})
	if err != nil {
		return WorkflowRunCancellation{}, err
	}
	if strings.TrimSpace(target.TemporalWorkflowID) == "" {
		return WorkflowRunCancellation{}, &AppError{
			Code:    "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED",
			Message: "workflow run has no Temporal workflow id",
		}
	}
	if err := c.client.CancelWorkflow(ctx, strings.TrimSpace(target.TemporalWorkflowID), ""); err != nil {
		return WorkflowRunCancellation{}, &AppError{
			Code:    "WORKFLOW_CANCEL_FAILED",
			Message: fmt.Sprintf("failed to cancel workflow: %v", err),
		}
	}
	status := "cancelled"
	if err := c.store.CancelWorkflowRun(ctx, WorkflowCancellationInput{
		TenantID:     strings.TrimSpace(input.TenantID),
		ProjectID:    strings.TrimSpace(target.ProjectID),
		RunID:        strings.TrimSpace(input.RunID),
		WorkflowType: strings.TrimSpace(target.WorkflowType),
		ActorUserID:  strings.TrimSpace(input.ActorUserID),
		RequestID:    strings.TrimSpace(input.RequestID),
		Status:       status,
	}); err != nil {
		return WorkflowRunCancellation{}, err
	}
	return WorkflowRunCancellation{RunID: strings.TrimSpace(input.RunID), Status: status}, nil
}

type SQLWorkflowCancellationStoreConfig struct {
	Queryer WriterEventSQLQueryer
	Execer  WriterAdmissionSQLExecer
}

type SQLWorkflowCancellationStore struct {
	queryer WriterEventSQLQueryer
	execer  WriterAdmissionSQLExecer
}

func NewSQLWorkflowCancellationStore(config SQLWorkflowCancellationStoreConfig) *SQLWorkflowCancellationStore {
	return &SQLWorkflowCancellationStore{queryer: config.Queryer, execer: config.Execer}
}

func (s *SQLWorkflowCancellationStore) GetWorkflowCancellationTarget(ctx context.Context, input WorkflowCancellationTargetInput) (WorkflowCancellationTarget, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return WorkflowCancellationTarget{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and run_id are required"}
	}
	if s.queryer == nil {
		return WorkflowCancellationTarget{}, &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "workflow cancellation store is not configured"}
	}
	query := `SELECT
  run_id::text,
  project_id::text,
  workflow_type,
  temporal_workflow_id
FROM workflow_runs
WHERE tenant_id::text = $1
  AND run_id::text = $2
LIMIT 1`
	rows, err := s.queryer.QueryContext(
		ctx,
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
	)
	if err != nil {
		return WorkflowCancellationTarget{}, &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return WorkflowCancellationTarget{}, &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: err.Error()}
		}
		return WorkflowCancellationTarget{}, &AppError{Code: "NOT_FOUND", Message: "workflow run not found"}
	}
	var runID string
	var projectID string
	var workflowType string
	var temporalWorkflowID sql.NullString
	if err := rows.Scan(&runID, &projectID, &workflowType, &temporalWorkflowID); err != nil {
		return WorkflowCancellationTarget{}, &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return WorkflowCancellationTarget{}, &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: err.Error()}
	}
	return WorkflowCancellationTarget{
		RunID:              runID,
		ProjectID:          projectID,
		WorkflowType:       workflowType,
		TemporalWorkflowID: temporalWorkflowID.String,
	}, nil
}

func (s *SQLWorkflowCancellationStore) CancelWorkflowRun(ctx context.Context, input WorkflowCancellationInput) error {
	if strings.TrimSpace(input.TenantID) == "" ||
		strings.TrimSpace(input.ProjectID) == "" ||
		strings.TrimSpace(input.RunID) == "" ||
		strings.TrimSpace(input.WorkflowType) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, run_id, and workflow_type are required"}
	}
	if s.execer == nil {
		return &AppError{Code: "WORKFLOW_BACKEND_UNCONFIGURED", Message: "workflow cancellation store is not configured"}
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
		return &AppError{Code: "VALIDATION_FAILED", Message: "workflow cancellation payload must be JSON serializable"}
	}
	query := `WITH workflow_update AS (
  UPDATE workflow_runs
  SET
    status = $4,
    message = $5,
    updated_at = now()
  WHERE tenant_id = $1::uuid
    AND run_id = $3::uuid
    AND project_id = $2::uuid
    AND status IN ('queued', 'running')
  RETURNING run_id, project_id, workflow_type
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
  'workflow.cancelled',
  next_sequence.sequence,
  $7::jsonb
FROM workflow_update
CROSS JOIN next_sequence
WHERE workflow_update.workflow_type = $6`
	result, err := s.execer.ExecContext(
		ctx,
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RunID),
		status,
		"cancelled",
		strings.TrimSpace(input.WorkflowType),
		string(payload),
	)
	if err != nil {
		return &AppError{Code: "WORKFLOW_CANCEL_FAILED", Message: err.Error()}
	}
	rowsAffected, err := result.RowsAffected()
	if err == nil && rowsAffected != 1 {
		return &AppError{Code: "WORKFLOW_RUN_NOT_FOUND", Message: "workflow run not found for cancellation"}
	}
	return nil
}
