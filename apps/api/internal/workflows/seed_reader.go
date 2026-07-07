package workflows

import (
	"context"
	"database/sql"
	"strings"
)

type ListSeedRunsInput struct {
	TenantID  string
	ProjectID string
}

type GetSeedRunInput struct {
	TenantID string
	RunID    string
}

type SeedRunReader interface {
	ListSeedRuns(context.Context, ListSeedRunsInput) ([]WorkflowRun, error)
	GetSeedRun(context.Context, GetSeedRunInput) (WorkflowRun, error)
}

type DisabledSeedRunReader struct{}

func NewDisabledSeedRunReader() *DisabledSeedRunReader {
	return &DisabledSeedRunReader{}
}

func (r *DisabledSeedRunReader) ListSeedRuns(_ context.Context, _ ListSeedRunsInput) ([]WorkflowRun, error) {
	return nil, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "seed run reader is not configured",
	}
}

func (r *DisabledSeedRunReader) GetSeedRun(_ context.Context, _ GetSeedRunInput) (WorkflowRun, error) {
	return WorkflowRun{}, &AppError{
		Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
		Message: "seed run reader is not configured",
	}
}

type SQLSeedRunReaderConfig struct {
	Queryer WriterEventSQLQueryer
	Limit   int
}

type SQLSeedRunReader struct {
	queryer WriterEventSQLQueryer
	limit   int
}

func NewSQLSeedRunReader(config SQLSeedRunReaderConfig) *SQLSeedRunReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLSeedRunReader{queryer: config.Queryer, limit: limit}
}

func (r *SQLSeedRunReader) ListSeedRuns(ctx context.Context, input ListSeedRunsInput) ([]WorkflowRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return nil, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and project_id are required",
		}
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "seed run reader is not configured",
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
  AND project_id::text = $2
  AND workflow_type = $3
ORDER BY created_at DESC
LIMIT $4`
	rows, err := querySeedRunRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		SeedWorkflowType,
		r.limit,
	)
	if err != nil {
		return nil, seedRunQueryFailed()
	}
	defer rows.Close()
	return scanWorkflowRunRows(rows)
}

func (r *SQLSeedRunReader) GetSeedRun(ctx context.Context, input GetSeedRunInput) (WorkflowRun, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.RunID) == "" {
		return WorkflowRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	if r.queryer == nil {
		return WorkflowRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "seed run reader is not configured",
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
  AND workflow_type = $3
LIMIT 1`
	rows, err := querySeedRunRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
		SeedWorkflowType,
	)
	if err != nil {
		return WorkflowRun{}, seedRunQueryFailed()
	}
	defer rows.Close()

	runs, err := scanWorkflowRunRows(rows)
	if err != nil {
		return WorkflowRun{}, err
	}
	if len(runs) == 0 {
		return WorkflowRun{}, &AppError{Code: "NOT_FOUND", Message: "seed run not found"}
	}
	return runs[0], nil
}

func scanWorkflowRunRows(rows WriterEventSQLRows) ([]WorkflowRun, error) {
	runs := []WorkflowRun{}
	for rows.Next() {
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
			return nil, seedRunQueryFailed()
		}
		runs = append(runs, WorkflowRun{
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
		})
	}
	if err := rows.Err(); err != nil {
		return nil, seedRunQueryFailed()
	}
	return runs, nil
}

func querySeedRunRows(ctx context.Context, queryer WriterEventSQLQueryer, tenantID string, query string, args ...any) (WriterEventSQLRows, error) {
	if tenantQueryer, ok := queryer.(WriterEventSQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return queryer.QueryContext(ctx, query, args...)
}

func seedRunQueryFailed() *AppError {
	return &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: "seed run query failed"}
}
