package workflows

import (
	"context"
	"database/sql"
	"strings"
)

type SQLWriterReaderConfig struct {
	Queryer WriterEventSQLQueryer
}

type SQLWriterReader struct {
	queryer WriterEventSQLQueryer
}

func NewSQLWriterReader(config SQLWriterReaderConfig) *SQLWriterReader {
	return &SQLWriterReader{queryer: config.Queryer}
}

func (r *SQLWriterReader) GetWriterRun(ctx context.Context, input GetWriterRunInput) (WriterRun, error) {
	if input.TenantID == "" || input.RunID == "" {
		return WriterRun{}, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	if r.queryer == nil {
		return WriterRun{}, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "writer reader is not configured",
		}
	}
	query := `SELECT
  run_id::text,
  project_id::text,
  status
FROM writer_runs
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
		return WriterRun{}, writerRunQueryFailed()
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return WriterRun{}, writerRunQueryFailed()
		}
		return WriterRun{}, &AppError{Code: "NOT_FOUND", Message: "writer run not found"}
	}
	var runID string
	var projectID string
	var status string
	if err := rows.Scan(&runID, &projectID, &status); err != nil {
		if err == sql.ErrNoRows {
			return WriterRun{}, &AppError{Code: "NOT_FOUND", Message: "writer run not found"}
		}
		return WriterRun{}, writerRunQueryFailed()
	}
	if err := rows.Err(); err != nil {
		return WriterRun{}, writerRunQueryFailed()
	}
	return WriterRun{
		RunID:     runID,
		TraceID:   traceIDForRun(runID),
		TenantID:  strings.TrimSpace(input.TenantID),
		ProjectID: projectID,
		Status:    status,
	}, nil
}

func writerRunQueryFailed() *AppError {
	return &AppError{Code: "WORKFLOW_QUERY_FAILED", Message: "writer run query failed"}
}
