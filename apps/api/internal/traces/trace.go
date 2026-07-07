package traces

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type EventQueryInput struct {
	TenantID    string
	ProjectID   string
	TraceID     string
	IncludeFull bool
}

type EventRecord struct {
	EventID        string         `json:"event_id"`
	TraceID        string         `json:"trace_id"`
	EventOrder     int            `json:"event_order"`
	EventType      string         `json:"event_type"`
	Payload        map[string]any `json:"payload"`
	RedactionLevel string         `json:"redaction_level"`
	CreatedAt      string         `json:"created_at"`
}

type Reader interface {
	ListEvents(context.Context, EventQueryInput) ([]EventRecord, error)
}

type ExportAuditInput struct {
	TenantID    string
	ProjectID   string
	TraceID     string
	ActorID     string
	RequestID   string
	IncludeFull bool
	EventCount  int
}

type ExportAuditor interface {
	RecordExport(context.Context, ExportAuditInput) error
}

type DisabledExportAuditor struct{}

func NewDisabledExportAuditor() DisabledExportAuditor {
	return DisabledExportAuditor{}
}

func (DisabledExportAuditor) RecordExport(context.Context, ExportAuditInput) error {
	return &AppError{
		Code:    "TRACE_AUDIT_BACKEND_UNCONFIGURED",
		Message: "trace export audit backend is not configured",
	}
}

type DisabledReader struct{}

func NewDisabledReader() DisabledReader {
	return DisabledReader{}
}

func (DisabledReader) ListEvents(context.Context, EventQueryInput) ([]EventRecord, error) {
	return nil, &AppError{
		Code:    "AGENT_TRACE_BACKEND_UNCONFIGURED",
		Message: "agent trace backend is not configured",
	}
}

type AccessInput struct {
	TenantID  string
	ProjectID string
	TraceID   string
	ActorID   string
}

type AccessChecker interface {
	CanViewFullTrace(context.Context, AccessInput) error
}

type DenyFullTraceAccessChecker struct{}

func NewDenyFullTraceAccessChecker() DenyFullTraceAccessChecker {
	return DenyFullTraceAccessChecker{}
}

func (DenyFullTraceAccessChecker) CanViewFullTrace(context.Context, AccessInput) error {
	return &AppError{
		Code:    "TRACE_ACCESS_DENIED",
		Message: "full trace access is not permitted",
	}
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "AGENT_TRACE_QUERY_FAILED"
}

type SQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type SQLQueryer interface {
	QueryContext(context.Context, string, ...any) (SQLRows, error)
}

type SQLReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLReader struct {
	queryer SQLQueryer
	limit   int
}

type SQLExportAuditorConfig struct {
	Queryer SQLQueryer
}

type SQLExportAuditor struct {
	queryer SQLQueryer
}

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLReader{queryer: config.Queryer, limit: limit}
}

func NewSQLExportAuditor(config SQLExportAuditorConfig) *SQLExportAuditor {
	return &SQLExportAuditor{queryer: config.Queryer}
}

type sqlDBQueryer struct {
	db *sql.DB
}

func NewSQLDBQueryer(db *sql.DB) SQLQueryer {
	return sqlDBQueryer{db: db}
}

func (q sqlDBQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (r *SQLReader) ListEvents(ctx context.Context, input EventQueryInput) ([]EventRecord, error) {
	if err := validateTraceInput(input); err != nil {
		return nil, err
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "AGENT_TRACE_BACKEND_UNCONFIGURED",
			Message: "agent trace backend is not configured",
		}
	}
	query := `SELECT
  e.event_id::text,
  e.trace_id,
  e.event_order,
  e.event_type,
  CASE WHEN $4::boolean OR e.redaction_level IN ('public', 'summary')
    THEN e.payload_jsonb
    ELSE '{}'::jsonb
  END::text,
  e.redaction_level,
  e.created_at::text
FROM agent_trace_events e
JOIN agent_traces t
  ON t.tenant_id = e.tenant_id
 AND t.trace_id = e.trace_id
WHERE e.tenant_id::text = $1
  AND t.project_id::text = $2
  AND e.trace_id = $3
ORDER BY e.event_order ASC
LIMIT $5`
	rows, err := r.queryer.QueryContext(
		ctx,
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.TraceID),
		input.IncludeFull,
		r.limit,
	)
	if err != nil {
		return nil, &AppError{Code: "AGENT_TRACE_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	records := []EventRecord{}
	for rows.Next() {
		var record EventRecord
		var payloadJSON string
		if err := rows.Scan(
			&record.EventID,
			&record.TraceID,
			&record.EventOrder,
			&record.EventType,
			&payloadJSON,
			&record.RedactionLevel,
			&record.CreatedAt,
		); err != nil {
			return nil, &AppError{Code: "AGENT_TRACE_QUERY_FAILED", Message: err.Error()}
		}
		record.Payload = decodePayload(payloadJSON)
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "AGENT_TRACE_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func (a *SQLExportAuditor) RecordExport(ctx context.Context, input ExportAuditInput) error {
	if err := validateExportAuditInput(input); err != nil {
		return err
	}
	if a.queryer == nil {
		return &AppError{
			Code:    "TRACE_AUDIT_BACKEND_UNCONFIGURED",
			Message: "trace export audit backend is not configured",
		}
	}
	metadata, err := json.Marshal(map[string]any{
		"trace_id":     strings.TrimSpace(input.TraceID),
		"actor_id":     strings.TrimSpace(input.ActorID),
		"include_full": input.IncludeFull,
		"event_count":  input.EventCount,
	})
	if err != nil {
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: err.Error()}
	}
	query := `INSERT INTO audit_logs (
  tenant_id, actor_user_id, action, resource_type, resource_id,
  project_id, run_id, request_id, metadata_jsonb
) VALUES (
  $1::uuid,
  CASE
    WHEN $2 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $2::uuid
    ELSE NULL
  END,
  'agent_trace.export',
  'agent_trace',
  NULL,
  $3::uuid,
  NULL,
  $4,
  $5::jsonb
) RETURNING audit_id::text`
	rows, err := a.queryer.QueryContext(
		ctx,
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ActorID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.RequestID),
		string(metadata),
	)
	if err != nil {
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return &AppError{Code: "TRACE_AUDIT_FAILED", Message: err.Error()}
		}
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: "audit insert did not return audit_id"}
	}
	var auditID string
	if err := rows.Scan(&auditID); err != nil {
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: err.Error()}
	}
	if strings.TrimSpace(auditID) == "" {
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: "audit insert returned empty audit_id"}
	}
	if err := rows.Err(); err != nil {
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: err.Error()}
	}
	return nil
}

func validateTraceInput(input EventQueryInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.TraceID) == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and trace_id are required",
		}
	}
	return nil
}

func validateExportAuditInput(input ExportAuditInput) error {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" || strings.TrimSpace(input.TraceID) == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id, project_id, and trace_id are required",
		}
	}
	return nil
}

func decodePayload(raw string) map[string]any {
	raw = strings.TrimSpace(raw)
	if raw == "" || raw == "{}" || raw == "null" {
		return map[string]any{}
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return map[string]any{"message": fmt.Sprintf("invalid trace payload: %s", raw)}
	}
	return decoded
}
