package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
)

type WriterEventSQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type WriterEventSQLQueryer interface {
	QueryContext(context.Context, string, ...any) (WriterEventSQLRows, error)
}

type WriterEventSQLTenantQueryer interface {
	QueryTenantContext(context.Context, string, string, ...any) (WriterEventSQLRows, error)
}

type SQLWriterEventReaderConfig struct {
	Queryer WriterEventSQLQueryer
	Limit   int
}

type SQLWriterEventReader struct {
	queryer WriterEventSQLQueryer
	limit   int
}

type sqlDBWriterEventQueryer struct {
	db *sql.DB
}

func NewSQLDBWriterEventQueryer(db *sql.DB) WriterEventSQLQueryer {
	return sqlDBWriterEventQueryer{db: db}
}

func (q sqlDBWriterEventQueryer) QueryContext(ctx context.Context, query string, args ...any) (WriterEventSQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (q sqlDBWriterEventQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (WriterEventSQLRows, error) {
	tx, err := q.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULL::uuid, false)", strings.TrimSpace(tenantID)); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, query, args...)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return &workflowTenantScopedRows{rows: rows, tx: tx}, nil
}

type workflowTenantScopedRows struct {
	rows WriterEventSQLRows
	tx   *sql.Tx
}

func (r *workflowTenantScopedRows) Next() bool {
	return r.rows.Next()
}

func (r *workflowTenantScopedRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *workflowTenantScopedRows) Close() error {
	closeErr := r.rows.Close()
	rowsErr := r.rows.Err()
	if closeErr != nil || rowsErr != nil {
		_ = r.tx.Rollback()
		if closeErr != nil {
			return closeErr
		}
		return rowsErr
	}
	return r.tx.Commit()
}

func (r *workflowTenantScopedRows) Err() error {
	return r.rows.Err()
}

func NewSQLWriterEventReader(config SQLWriterEventReaderConfig) *SQLWriterEventReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLWriterEventReader{queryer: config.Queryer, limit: limit}
}

func (r *SQLWriterEventReader) ListWriterEvents(ctx context.Context, input ListWriterEventsInput) ([]WriterEvent, error) {
	if input.TenantID == "" || input.RunID == "" {
		return nil, &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and run_id are required",
		}
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "WORKFLOW_BACKEND_UNCONFIGURED",
			Message: "writer event reader is not configured",
		}
	}
	query := `WITH after_cursor AS (
  SELECT sequence
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND run_id::text = $2
    AND event_id::text = $3
  LIMIT 1
),
cursor_state AS (
  SELECT ($3 = '' OR EXISTS (SELECT 1 FROM after_cursor)) AS cursor_found
),
event_rows AS (
  SELECT
    event_id::text,
    run_id::text,
    project_id::text,
    sequence,
    event_type,
    payload_jsonb::text,
    created_at::text
  FROM workflow_events
  WHERE tenant_id::text = $1
    AND run_id::text = $2
    AND ($3 = '' OR sequence > COALESCE((SELECT sequence FROM after_cursor), -1))
  ORDER BY sequence ASC
  LIMIT $4
)
SELECT
  cursor_state.cursor_found,
  event_rows.event_id,
  event_rows.run_id,
  event_rows.project_id,
  event_rows.sequence,
  event_rows.event_type,
  event_rows.payload_jsonb,
  event_rows.created_at
FROM cursor_state
LEFT JOIN event_rows ON true
ORDER BY event_rows.sequence ASC NULLS LAST`
	rows, err := queryWorkflowEventRows(
		ctx,
		r.queryer,
		strings.TrimSpace(input.TenantID),
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.RunID),
		strings.TrimSpace(input.AfterEventID),
		r.limit,
	)
	if err != nil {
		return nil, workflowEventQueryFailed()
	}
	defer rows.Close()

	records := []WriterEvent{}
	for rows.Next() {
		var cursorFound bool
		var eventID sql.NullString
		var runID sql.NullString
		var projectID sql.NullString
		var sequence sql.NullInt64
		var eventType sql.NullString
		var payloadJSON sql.NullString
		var createdAt sql.NullString
		if err := rows.Scan(
			&cursorFound,
			&eventID,
			&runID,
			&projectID,
			&sequence,
			&eventType,
			&payloadJSON,
			&createdAt,
		); err != nil {
			return nil, workflowEventQueryFailed()
		}
		if !cursorFound {
			return nil, &AppError{
				Code:    "EVENT_CURSOR_NOT_FOUND",
				Message: "writer event cursor not found",
			}
		}
		if !eventID.Valid {
			continue
		}
		records = append(records, WriterEvent{
			EventID:   eventID.String,
			RunID:     runID.String,
			ProjectID: projectID.String,
			Sequence:  int(sequence.Int64),
			EventType: eventType.String,
			Payload:   SanitizeWorkflowEventPayload(decodeWriterEventPayload(payloadJSON.String)),
			CreatedAt: createdAt.String,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, workflowEventQueryFailed()
	}
	return records, nil
}

func decodeWriterEventPayload(raw string) map[string]any {
	var payload map[string]any
	if err := json.Unmarshal([]byte(raw), &payload); err != nil || payload == nil {
		return map[string]any{}
	}
	return payload
}
