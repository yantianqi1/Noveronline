package workflows

import (
	"context"
	"database/sql"
	"strings"
)

type GetWorkflowRunInput struct {
	TenantID string
	RunID    string
}

type WorkflowRun struct {
	RunID        string `json:"run_id"`
	WorkflowType string `json:"workflow_type"`
	ProjectID    string `json:"project_id"`
	Status       string `json:"status"`
	Progress     int    `json:"progress"`
	Message      string `json:"message"`
	ErrorCode    string `json:"error_code"`
	ErrorMessage string `json:"error_message"`
	CreatedAt    string `json:"created_at"`
	UpdatedAt    string `json:"updated_at"`
}

type WorkflowReader interface {
	GetWorkflowRun(context.Context, GetWorkflowRunInput) (WorkflowRun, error)
}

type DisabledWorkflowReader struct{}

func NewDisabledWorkflowReader() *DisabledWorkflowReader {
	return &DisabledWorkflowReader{}
}

func (r *DisabledWorkflowReader) GetWorkflowRun(_ context.Context, _ GetWorkflowRunInput) (WorkflowRun, error) {
	return WorkflowRun{}, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "workflow reader is not configured",
	}
}

type SQLWorkflowReaderConfig struct {
	Queryer WriterEventSQLQueryer
}

type SQLWorkflowReader struct {
	queryer WriterEventSQLQueryer
}

func NewSQLWorkflowReader(config SQLWorkflowReaderConfig) *SQLWorkflowReader {
	return &SQLWorkflowReader{queryer: config.Queryer}
}

func (r *SQLWorkflowReader) GetWorkflowRun(ctx context.Context, input GetWorkflowRunInput) (WorkflowRun, error) {
	if input.TenantID == "" || input.RunID == "" {
		return WorkflowRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	if r.queryer == nil {
		return WorkflowRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "workflow reader is not configured",
		}
	}
	query := `SELECT
  run_id::text,
  workflow_type,
  project_id::text,
  status,
  progress,
  message,
  error_code,
  error_message,
  created_at::text,
  updated_at::text
FROM workflow_runs
WHERE tenant_id::text = $1
  AND run_id::text = $2
LIMIT 1`
	rows, err := r.queryer.QueryContext(
		ctx,
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
	)
	if err != nil {
		return WorkflowRun{}, workflowRunQueryFailed()
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return WorkflowRun{}, workflowRunQueryFailed()
		}
		return WorkflowRun{}, &AppError{Code: "NOT_FOUND", Message: "workflow run not found"}
	}
	var runID string
	var workflowType string
	var projectID string
	var status string
	var progress int
	var message sql.NullString
	var errorCode sql.NullString
	var errorMessage sql.NullString
	var createdAt string
	var updatedAt string
	if err := rows.Scan(
		&runID,
		&workflowType,
		&projectID,
		&status,
		&progress,
		&message,
		&errorCode,
		&errorMessage,
		&createdAt,
		&updatedAt,
	); err != nil {
		if err == sql.ErrNoRows {
			return WorkflowRun{}, &AppError{Code: "NOT_FOUND", Message: "workflow run not found"}
		}
		return WorkflowRun{}, workflowRunQueryFailed()
	}
	if err := rows.Err(); err != nil {
		return WorkflowRun{}, workflowRunQueryFailed()
	}
	return WorkflowRun{
		RunID:        runID,
		WorkflowType: workflowType,
		ProjectID:    projectID,
		Status:       status,
		Progress:     progress,
		Message:      message.String,
		ErrorCode:    errorCode.String,
		ErrorMessage: errorMessage.String,
		CreatedAt:    createdAt,
		UpdatedAt:    updatedAt,
	}, nil
}

func workflowRunQueryFailed() *AppError {
	return &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: "workflow run query failed"}
}
