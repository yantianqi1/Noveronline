package traces

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
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

type SQLTenantQueryer interface {
	QueryTenantContext(context.Context, string, string, ...any) (SQLRows, error)
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

func (q sqlDBQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
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
	return &tenantScopedRows{rows: rows, tx: tx}, nil
}

type tenantScopedRows struct {
	rows SQLRows
	tx   *sql.Tx
}

func (r *tenantScopedRows) Next() bool             { return r.rows.Next() }
func (r *tenantScopedRows) Scan(dest ...any) error { return r.rows.Scan(dest...) }
func (r *tenantScopedRows) Err() error             { return r.rows.Err() }
func (r *tenantScopedRows) Close() error {
	if err := r.rows.Close(); err != nil {
		_ = r.tx.Rollback()
		return err
	}
	return r.tx.Commit()
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
	rows, err := queryTraceRows(
		ctx,
		r.queryer,
		input.TenantID,
		query,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		strings.TrimSpace(input.TraceID),
		input.IncludeFull,
		r.limit,
	)
	if err != nil {
		return nil, traceQueryError()
	}

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
			_ = rows.Close()
			return nil, traceQueryError()
		}
		record.Payload = decodePayload(payloadJSON)
		if !input.IncludeFull {
			record.Payload = sanitizeTraceMap(record.Payload)
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, traceQueryError()
	}
	if err := rows.Close(); err != nil {
		return nil, traceQueryError()
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
		return traceAuditError()
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
		return traceAuditError()
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return traceAuditError()
		}
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: "audit insert did not return audit_id"}
	}
	var auditID string
	if err := rows.Scan(&auditID); err != nil {
		return traceAuditError()
	}
	if strings.TrimSpace(auditID) == "" {
		return &AppError{Code: "TRACE_AUDIT_FAILED", Message: "audit insert returned empty audit_id"}
	}
	if err := rows.Err(); err != nil {
		return traceAuditError()
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
		return map[string]any{"message": "invalid trace payload"}
	}
	return decoded
}

func queryTraceRows(ctx context.Context, queryer SQLQueryer, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, strings.TrimSpace(tenantID), query, args...)
	}
	return queryer.QueryContext(ctx, query, args...)
}

func traceQueryError() error {
	return &AppError{Code: "AGENT_TRACE_QUERY_FAILED", Message: "agent trace query failed"}
}

func traceAuditError() error {
	return &AppError{Code: "TRACE_AUDIT_FAILED", Message: "trace export audit failed"}
}

func sanitizeTraceMap(input map[string]any) map[string]any {
	output := map[string]any{}
	for key, value := range input {
		if isSensitiveTraceKey(key) {
			continue
		}
		output[key] = sanitizeTraceValue(value)
	}
	return output
}

func sanitizeTraceValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeTraceMap(typed)
	case []any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, sanitizeTraceValue(item))
		}
		return items
	default:
		return value
	}
}

func isSensitiveTraceKey(key string) bool {
	switch strings.ToLower(strings.TrimSpace(key)) {
	case "api_key", "apikey", "authorization", "body", "body_text", "content", "content_text", "credential_ref", "draft", "encrypted_api_key", "manuscript", "prompt", "raw_body", "raw_content", "raw_text", "response", "source_material", "source_text", "text":
		return true
	default:
		return false
	}
}
