package llm

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
)

func TestSQLTelemetryReaderListsActivityWithTenantProjectRunFilters(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"activity-1",
				"project-123",
				"run_123",
				"writer_composer",
				"channel-1",
				"model-1",
				"failed",
				11,
				17,
				1200,
				0.0045,
				`{"code":"LLM_PROVIDER_ERROR","message":"provider rejected request"}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	records, err := reader.ListActivity(context.Background(), ActivityQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		RunID:     "run_123",
		ModuleKey: "writer_composer",
	})

	if err != nil {
		t.Fatalf("list activity: %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("expected one record, got %#v", records)
	}
	if records[0].Error["code"] != "LLM_PROVIDER_ERROR" || records[0].PromptTokens != 11 || records[0].CompletionTokens != 17 {
		t.Fatalf("unexpected activity record: %#v", records[0])
	}
	if !strings.Contains(queryer.query, "FROM llm_activity") || !strings.Contains(queryer.query, "run_id::text = $3") || !strings.Contains(queryer.query, "module_key = $4") {
		t.Fatalf("expected tenant/project/run/module query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "run_123", "writer_composer", 100}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLTelemetryReaderListsUsageWithTenantProjectRunFilters(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"llm_tokens",
				28.0,
				"tokens",
				"writer_composer",
				"run_123",
			}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer, Limit: 25})

	records, err := reader.ListUsage(context.Background(), UsageQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		RunID:     "run_123",
	})

	if err != nil {
		t.Fatalf("list usage: %v", err)
	}
	if len(records) != 1 || records[0].Quantity != 28 || records[0].UsageType != "llm_tokens" {
		t.Fatalf("unexpected usage records: %#v", records)
	}
	if !strings.Contains(queryer.query, "FROM usage_events") || !strings.Contains(queryer.query, "run_id::text = $3") {
		t.Fatalf("expected usage query filters, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "run_123", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLTelemetryReaderLimitsUsageToLLMTokenEvents(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"llm_tokens",
				34.0,
				"tokens",
				"worldline_director",
				"550e8400-e29b-41d4-a716-446655440000",
			}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	records, err := reader.ListUsage(context.Background(), UsageQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		RunID:     "550e8400-e29b-41d4-a716-446655440000",
		ModuleKey: "worldline_director",
	})

	if err != nil {
		t.Fatalf("list usage: %v", err)
	}
	if len(records) != 1 || records[0].UsageType != "llm_tokens" || records[0].ModuleKey != "worldline_director" {
		t.Fatalf("unexpected usage records: %#v", records)
	}
	if !strings.Contains(queryer.query, "usage_type = 'llm_tokens'") {
		t.Fatalf("expected LLM usage query to exclude non-token usage events, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "550e8400-e29b-41d4-a716-446655440000", "worldline_director", 100}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLTelemetryReaderSanitizesActivityErrorPayload(t *testing.T) {
	queryer := &recordingSQLQueryer{
		rows: &fakeSQLRows{
			values: [][]any{{
				"activity-1",
				"project-123",
				"550e8400-e29b-41d4-a716-446655440000",
				"worldline_director",
				"channel-1",
				"model-1",
				"failed",
				0,
				0,
				1200,
				0.0,
				`{"code":"LLM_PROVIDER_ERROR","message":"provider failed","api_key":"sk-leaked","prompt":"private prompt","candidate_body":"hidden candidate","nested":{"credential_ref":"secret-ref","source_material":"private source","safe":"visible"},"events":[{"event_body":"secret event","summary":"visible summary"}]}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	records, err := reader.ListActivity(context.Background(), ActivityQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		RunID:     "550e8400-e29b-41d4-a716-446655440000",
		ModuleKey: "worldline_director",
	})

	if err != nil {
		t.Fatalf("list activity: %v", err)
	}
	if len(records) != 1 {
		t.Fatalf("expected one activity record, got %#v", records)
	}
	if records[0].Error["code"] != "LLM_PROVIDER_ERROR" || records[0].Error["message"] != "provider failed" {
		t.Fatalf("expected safe error summary, got %#v", records[0].Error)
	}
	nested := records[0].Error["nested"].(map[string]any)
	if nested["safe"] != "visible" {
		t.Fatalf("expected safe nested error field, got %#v", nested)
	}
	encoded := strings.ToLower(fmt.Sprint(records[0].Error))
	for _, forbidden := range []string{"api_key", "sk-leaked", "prompt", "private prompt", "candidate_body", "hidden candidate", "credential_ref", "secret-ref", "source_material", "private source", "event_body", "secret event"} {
		if strings.Contains(encoded, forbidden) {
			t.Fatalf("activity error payload leaked %q: %#v", forbidden, records[0].Error)
		}
	}
}

func TestSQLTelemetryReaderSanitizesQueryExceptionMessage(t *testing.T) {
	queryer := &recordingSQLQueryer{
		err: errors.New("driver failed api_key=sk-leaked prompt=private credential_ref=secret-ref"),
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	_, err := reader.ListActivity(context.Background(), ActivityQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		RunID:     "550e8400-e29b-41d4-a716-446655440000",
		ModuleKey: "worldline_director",
	})

	if code := ErrorCode(err); code != "LLM_ACTIVITY_QUERY_FAILED" {
		t.Fatalf("expected telemetry query error, got %s (%v)", code, err)
	}
	if err == nil || err.Error() != "LLM activity query failed" {
		t.Fatalf("expected stable public error message, got %v", err)
	}
	encoded := strings.ToLower(err.Error())
	for _, forbidden := range []string{"api_key", "sk-leaked", "prompt", "private", "credential_ref", "secret-ref"} {
		if strings.Contains(encoded, forbidden) {
			t.Fatalf("query error leaked %q: %v", forbidden, err)
		}
	}
}

func TestSQLTelemetryReaderSanitizesUsageQueryExceptionMessage(t *testing.T) {
	queryer := &recordingSQLQueryer{
		err: errors.New("usage driver failed api_key=sk-leaked prompt=private credential_ref=secret-ref"),
	}
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: queryer})

	_, err := reader.ListUsage(context.Background(), UsageQueryInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		RunID:     "550e8400-e29b-41d4-a716-446655440000",
		ModuleKey: "worldline_director",
	})

	if code := ErrorCode(err); code != "LLM_ACTIVITY_QUERY_FAILED" {
		t.Fatalf("expected telemetry query error, got %s (%v)", code, err)
	}
	if err == nil || err.Error() != "LLM activity query failed" {
		t.Fatalf("expected stable public error message, got %v", err)
	}
	encoded := strings.ToLower(err.Error())
	for _, forbidden := range []string{"api_key", "sk-leaked", "prompt", "private", "credential_ref", "secret-ref"} {
		if strings.Contains(encoded, forbidden) {
			t.Fatalf("usage query error leaked %q: %v", forbidden, err)
		}
	}
}

func TestSQLTelemetryReaderRejectsMissingTenantProject(t *testing.T) {
	reader := NewSQLTelemetryReader(SQLTelemetryConfig{Queryer: &recordingSQLQueryer{}})

	_, err := reader.ListActivity(context.Background(), ActivityQueryInput{TenantID: "", ProjectID: "project-123"})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error, got %s (%v)", code, err)
	}
}

type recordingSQLQueryer struct {
	query string
	args  []any
	rows  *fakeSQLRows
	err   error
}

func (q *recordingSQLQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	q.query = query
	q.args = append([]any(nil), args...)
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return nil, errors.New("no rows configured")
	}
	return q.rows, nil
}

type fakeSQLRows struct {
	values   [][]any
	index    int
	err      error
	closeErr error
}

func (r *fakeSQLRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeSQLRows) Scan(dest ...any) error {
	if r.index >= len(r.values) {
		return errors.New("scan past end")
	}
	row := r.values[r.index]
	r.index++
	for index, value := range row {
		switch target := dest[index].(type) {
		case *string:
			*target = value.(string)
		case *int:
			*target = value.(int)
		case *int64:
			*target = value.(int64)
		case **int64:
			if value == nil {
				*target = nil
			} else {
				parsed := value.(int64)
				*target = &parsed
			}
		case *float64:
			*target = value.(float64)
		case *bool:
			*target = value.(bool)
		default:
			return errors.New("unsupported scan target")
		}
	}
	return nil
}

func (r *fakeSQLRows) Close() error {
	return r.closeErr
}

func (r *fakeSQLRows) Err() error {
	return r.err
}
