package llm

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

type ActivityQueryInput struct {
	TenantID  string
	ProjectID string
	RunID     string
	ModuleKey string
}

type ActivityRecord struct {
	ActivityID       string         `json:"activity_id"`
	ProjectID        string         `json:"project_id"`
	RunID            string         `json:"run_id,omitempty"`
	ModuleKey        string         `json:"module_key"`
	ChannelID        string         `json:"channel_id,omitempty"`
	ModelID          string         `json:"model_id,omitempty"`
	Status           string         `json:"status"`
	PromptTokens     int            `json:"prompt_tokens,omitempty"`
	CompletionTokens int            `json:"completion_tokens,omitempty"`
	LatencyMS        int            `json:"latency_ms,omitempty"`
	CostEstimate     float64        `json:"cost_estimate,omitempty"`
	Error            map[string]any `json:"error,omitempty"`
	CreatedAt        string         `json:"created_at"`
}

type UsageQueryInput struct {
	TenantID  string
	ProjectID string
	RunID     string
	ModuleKey string
}

type UsageRecord struct {
	UsageType string  `json:"usage_type"`
	Quantity  float64 `json:"quantity"`
	Unit      string  `json:"unit"`
	ModuleKey string  `json:"module_key,omitempty"`
	RunID     string  `json:"run_id,omitempty"`
}

type TelemetryReader interface {
	ListActivity(context.Context, ActivityQueryInput) ([]ActivityRecord, error)
	ListUsage(context.Context, UsageQueryInput) ([]UsageRecord, error)
	BillingUsage(context.Context, BillingUsageQuery) ([]BillingUsageRecord, error)
}

type DisabledTelemetryReader struct{}

func NewDisabledTelemetryReader() DisabledTelemetryReader {
	return DisabledTelemetryReader{}
}

func (DisabledTelemetryReader) ListActivity(context.Context, ActivityQueryInput) ([]ActivityRecord, error) {
	return nil, &AppError{
		Code:    "LLM_ACTIVITY_BACKEND_UNCONFIGURED",
		Message: "LLM activity backend is not configured",
	}
}

func (DisabledTelemetryReader) ListUsage(context.Context, UsageQueryInput) ([]UsageRecord, error) {
	return nil, &AppError{
		Code:    "LLM_ACTIVITY_BACKEND_UNCONFIGURED",
		Message: "LLM usage backend is not configured",
	}
}

func (DisabledTelemetryReader) BillingUsage(context.Context, BillingUsageQuery) ([]BillingUsageRecord, error) {
	return nil, &AppError{
		Code:    "LLM_ACTIVITY_BACKEND_UNCONFIGURED",
		Message: "LLM billing usage backend is not configured",
	}
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

type SQLTenantWriteQueryer interface {
	QueryTenantWriteContext(context.Context, string, string, ...any) (SQLRows, error)
}

type SQLTelemetryConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLTelemetryReader struct {
	queryer SQLQueryer
	limit   int
}

func NewSQLTelemetryReader(config SQLTelemetryConfig) *SQLTelemetryReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 100
	}
	return &SQLTelemetryReader{
		queryer: config.Queryer,
		limit:   limit,
	}
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
	return &tenantScopedWriteRows{rows: rows, tx: tx}, nil
}

type transactionFinalizer interface {
	Commit() error
	Rollback() error
}

type tenantScopedWriteRows struct {
	rows      SQLRows
	tx        transactionFinalizer
	exhausted bool
	failed    bool
}

func (r *tenantScopedWriteRows) Next() bool {
	if r.failed {
		return false
	}
	if r.rows.Next() {
		return true
	}
	if r.rows.Err() != nil {
		r.failed = true
	} else {
		r.exhausted = true
	}
	return false
}

func (r *tenantScopedWriteRows) Scan(dest ...any) error {
	err := r.rows.Scan(dest...)
	if err != nil {
		r.failed = true
	}
	return err
}

func (r *tenantScopedWriteRows) Close() error {
	closeErr := r.rows.Close()
	if closeErr != nil || r.failed || !r.exhausted {
		rollbackErr := r.tx.Rollback()
		if closeErr != nil {
			return closeErr
		}
		return rollbackErr
	}
	return r.tx.Commit()
}

func (r *tenantScopedWriteRows) Err() error {
	err := r.rows.Err()
	if err != nil {
		r.failed = true
	}
	return err
}

func (q sqlDBQueryer) QueryTenantWriteContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	tx, err := q.db.BeginTx(ctx, nil)
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

func (r *tenantScopedRows) Next() bool {
	return r.rows.Next()
}

func (r *tenantScopedRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *tenantScopedRows) Close() error {
	rowsErr := r.rows.Close()
	if rowsErr != nil {
		_ = r.tx.Rollback()
		return rowsErr
	}
	return r.tx.Commit()
}

func (r *tenantScopedRows) Err() error {
	return r.rows.Err()
}

func (r *SQLTelemetryReader) ListActivity(ctx context.Context, input ActivityQueryInput) ([]ActivityRecord, error) {
	if err := validateTelemetryInput(input.TenantID, input.ProjectID); err != nil {
		return nil, err
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "LLM_ACTIVITY_BACKEND_UNCONFIGURED",
			Message: "LLM activity backend is not configured",
		}
	}
	where, args := telemetryWhere(input.TenantID, input.ProjectID, input.RunID, input.ModuleKey)
	query := fmt.Sprintf(`SELECT
  activity_id::text,
  project_id::text,
  COALESCE(run_id::text, ''),
  module_key,
  COALESCE(channel_id::text, ''),
  COALESCE(model_id, ''),
  status,
  COALESCE(prompt_tokens, 0),
  COALESCE(completion_tokens, 0),
  COALESCE(latency_ms, 0),
  COALESCE(cost_estimate, 0)::float8,
  COALESCE(error_jsonb, '{}'::jsonb)::text,
  created_at::text
FROM llm_activity
WHERE %s
ORDER BY created_at DESC
LIMIT $%d`, where, len(args)+1)
	args = append(args, r.limit)
	rows, err := r.queryRows(ctx, input.TenantID, query, args...)
	if err != nil {
		return nil, telemetryQueryError()
	}

	records := []ActivityRecord{}
	for rows.Next() {
		var record ActivityRecord
		var errorJSON string
		if err := rows.Scan(
			&record.ActivityID,
			&record.ProjectID,
			&record.RunID,
			&record.ModuleKey,
			&record.ChannelID,
			&record.ModelID,
			&record.Status,
			&record.PromptTokens,
			&record.CompletionTokens,
			&record.LatencyMS,
			&record.CostEstimate,
			&errorJSON,
			&record.CreatedAt,
		); err != nil {
			_ = rows.Close()
			return nil, telemetryQueryError()
		}
		record.Error = decodeErrorJSON(errorJSON)
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, telemetryQueryError()
	}
	if err := rows.Close(); err != nil {
		return nil, telemetryQueryError()
	}
	return records, nil
}

func (r *SQLTelemetryReader) ListUsage(ctx context.Context, input UsageQueryInput) ([]UsageRecord, error) {
	if err := validateTelemetryInput(input.TenantID, input.ProjectID); err != nil {
		return nil, err
	}
	if r.queryer == nil {
		return nil, &AppError{
			Code:    "LLM_ACTIVITY_BACKEND_UNCONFIGURED",
			Message: "LLM usage backend is not configured",
		}
	}
	where, args := telemetryWhere(input.TenantID, input.ProjectID, input.RunID, input.ModuleKey)
	where = where + " AND usage_type = 'llm_tokens'"
	query := fmt.Sprintf(`WITH normalized_usage AS (
  SELECT
    tenant_id,
    project_id,
    run_id,
    module_key,
    usage_type,
    quantity,
    unit,
    NULLIF(BTRIM(metadata_jsonb->>'provider_call_id'), '') AS provider_call_id,
    created_at,
    usage_event_id
  FROM usage_events
  WHERE %s
),
conflicting_calls AS (
  SELECT project_id, run_id, module_key, usage_type, provider_call_id
  FROM normalized_usage
  WHERE provider_call_id IS NOT NULL
  GROUP BY project_id, run_id, module_key, usage_type, provider_call_id
  HAVING MIN(quantity) <> MAX(quantity) OR MIN(unit) <> MAX(unit)
),
deduplicated_usage AS (
  SELECT DISTINCT ON (
    tenant_id,
    project_id,
    run_id,
    module_key,
    usage_type,
    unit,
    COALESCE(provider_call_id, usage_event_id::text)
  )
    usage_type,
    quantity,
    unit,
    module_key,
    run_id,
    created_at,
    usage_event_id
  FROM normalized_usage
  ORDER BY
    tenant_id,
    project_id,
    run_id,
    module_key,
    usage_type,
    unit,
    COALESCE(provider_call_id, usage_event_id::text),
    created_at,
    usage_event_id
)
SELECT
  usage_type,
  CASE
    WHEN EXISTS (SELECT 1 FROM conflicting_calls) THEN -1::float8
    ELSE COALESCE(SUM(quantity), 0)::float8
  END,
  unit,
  COALESCE(module_key, ''),
  COALESCE(run_id::text, '')
FROM deduplicated_usage
GROUP BY usage_type, unit, module_key, run_id
ORDER BY usage_type, module_key, run_id
LIMIT $%d`, where, len(args)+1)
	args = append(args, r.limit)
	rows, err := r.queryRows(ctx, input.TenantID, query, args...)
	if err != nil {
		return nil, telemetryQueryError()
	}

	records := []UsageRecord{}
	for rows.Next() {
		var record UsageRecord
		if err := rows.Scan(
			&record.UsageType,
			&record.Quantity,
			&record.Unit,
			&record.ModuleKey,
			&record.RunID,
		); err != nil {
			_ = rows.Close()
			return nil, telemetryQueryError()
		}
		if !finiteNonNegative(record.Quantity) || record.Unit != "tokens" {
			_ = rows.Close()
			return nil, telemetryQueryError()
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, telemetryQueryError()
	}
	if err := rows.Close(); err != nil {
		return nil, telemetryQueryError()
	}
	return records, nil
}

func (r *SQLTelemetryReader) queryRows(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := r.queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, tenantID, query, args...)
	}
	return r.queryer.QueryContext(ctx, query, args...)
}

func telemetryQueryError() error {
	return &AppError{
		Code:    "LLM_ACTIVITY_QUERY_FAILED",
		Message: "LLM activity query failed",
	}
}

func SanitizeActivityRecords(records []ActivityRecord) []ActivityRecord {
	sanitized := make([]ActivityRecord, 0, len(records))
	for _, record := range records {
		record.Error = SanitizeTelemetryPayload(record.Error)
		sanitized = append(sanitized, record)
	}
	return sanitized
}

func SanitizeTelemetryPayload(payload map[string]any) map[string]any {
	if len(payload) == 0 {
		return nil
	}
	return sanitizeTelemetryMap(payload)
}

func validateTelemetryInput(tenantID string, projectID string) error {
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(projectID) == "" {
		return &AppError{
			Code:    "VALIDATION_FAILED",
			Message: "tenant_id and project_id are required",
		}
	}
	return nil
}

func telemetryWhere(tenantID string, projectID string, runID string, moduleKey string) (string, []any) {
	clauses := []string{"tenant_id::text = $1", "project_id::text = $2"}
	args := []any{strings.TrimSpace(tenantID), strings.TrimSpace(projectID)}
	if runID = strings.TrimSpace(runID); runID != "" {
		args = append(args, runID)
		clauses = append(clauses, fmt.Sprintf("run_id::text = $%d", len(args)))
	}
	if moduleKey = strings.TrimSpace(moduleKey); moduleKey != "" {
		args = append(args, moduleKey)
		clauses = append(clauses, fmt.Sprintf("module_key = $%d", len(args)))
	}
	return strings.Join(clauses, " AND "), args
}

func decodeErrorJSON(raw string) map[string]any {
	raw = strings.TrimSpace(raw)
	if raw == "" || raw == "{}" || raw == "null" {
		return nil
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return map[string]any{"message": "unparseable error payload"}
	}
	return sanitizeTelemetryMap(decoded)
}

func sanitizeTelemetryMap(input map[string]any) map[string]any {
	output := map[string]any{}
	for key, value := range input {
		if isSensitiveTelemetryKey(key) {
			continue
		}
		output[key] = sanitizeTelemetryValue(value)
	}
	return output
}

func sanitizeTelemetryValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeTelemetryMap(typed)
	case []any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, sanitizeTelemetryValue(item))
		}
		return items
	default:
		return value
	}
}

func isSensitiveTelemetryKey(key string) bool {
	switch strings.ToLower(strings.TrimSpace(key)) {
	case "api_key", "apikey", "authorization", "body", "body_text", "candidate_body", "candidate_event_body", "content", "content_text", "credential_ref", "draft", "encrypted_api_key", "event_body", "manuscript", "prompt", "raw_body", "raw_content", "raw_text", "response", "source_material", "source_text", "text":
		return true
	default:
		return false
	}
}
