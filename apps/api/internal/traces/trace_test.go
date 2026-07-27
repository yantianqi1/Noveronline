package traces

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLReaderListsTraceEventsWithDefaultRedaction(t *testing.T) {
	queryer := &recordingTraceQueryer{
		rows: &fakeTraceRows{
			values: [][]any{{
				"event-1",
				"trace-1",
				1,
				"prompt_snapshot",
				`{}`,
				"full",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer})

	records, err := reader.ListEvents(context.Background(), EventQueryInput{
		TenantID:    "tenant-123",
		ProjectID:   "project-123",
		TraceID:     "trace-1",
		IncludeFull: false,
	})

	if err != nil {
		t.Fatalf("list trace events: %v", err)
	}
	if len(records) != 1 || records[0].EventType != "prompt_snapshot" || len(records[0].Payload) != 0 {
		t.Fatalf("unexpected records: %#v", records)
	}
	if !strings.Contains(queryer.query, "FROM agent_trace_events") || !strings.Contains(queryer.query, "JOIN agent_traces") {
		t.Fatalf("expected trace event query, got %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "CASE WHEN $4::boolean") {
		t.Fatalf("expected SQL-level redaction gate, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "trace-1", false, 100}) {
		t.Fatalf("unexpected args: %#v", queryer.args)
	}
}

func TestSQLReaderListsFullTraceEventsWhenAuthorized(t *testing.T) {
	queryer := &recordingTraceQueryer{
		rows: &fakeTraceRows{
			values: [][]any{{
				"event-1",
				"trace-1",
				1,
				"prompt_snapshot",
				`{"instruction":"写下一场雨夜谈判"}`,
				"full",
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLReader(SQLReaderConfig{Queryer: queryer, Limit: 25})

	records, err := reader.ListEvents(context.Background(), EventQueryInput{
		TenantID:    "tenant-123",
		ProjectID:   "project-123",
		TraceID:     "trace-1",
		IncludeFull: true,
	})

	if err != nil {
		t.Fatalf("list trace events: %v", err)
	}
	if records[0].Payload["instruction"] != "写下一场雨夜谈判" {
		t.Fatalf("expected full payload, got %#v", records[0])
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-123", "project-123", "trace-1", true, 25}) {
		t.Fatalf("unexpected args: %#v", queryer.args)
	}
}

func TestSQLReaderRejectsMissingTraceContext(t *testing.T) {
	reader := NewSQLReader(SQLReaderConfig{Queryer: &recordingTraceQueryer{}})

	_, err := reader.ListEvents(context.Background(), EventQueryInput{TenantID: "tenant-123", ProjectID: "", TraceID: "trace-1"})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation error, got %s (%v)", code, err)
	}
}

func TestSQLExportAuditorRecordsTraceExportAudit(t *testing.T) {
	queryer := &recordingTraceQueryer{
		rows: &fakeTraceRows{
			values: [][]any{{"audit-1"}},
		},
	}
	auditor := NewSQLExportAuditor(SQLExportAuditorConfig{Queryer: queryer})

	err := auditor.RecordExport(context.Background(), ExportAuditInput{
		TenantID:    "tenant-123",
		ProjectID:   "project-123",
		TraceID:     "trace-1",
		ActorID:     "user-123",
		RequestID:   "req-export",
		IncludeFull: true,
		EventCount:  3,
	})

	if err != nil {
		t.Fatalf("record export audit: %v", err)
	}
	if !strings.Contains(queryer.query, "INSERT INTO audit_logs") || !strings.Contains(queryer.query, "agent_trace.export") {
		t.Fatalf("expected audit insert query, got %s", queryer.query)
	}
	if len(queryer.args) != 5 {
		t.Fatalf("unexpected audit args: %#v", queryer.args)
	}
	if queryer.writeTenantID != "tenant-123" {
		t.Fatalf("audit write lost tenant transaction context: %#v", queryer)
	}
	if queryer.args[0] != "tenant-123" || queryer.args[1] != "user-123" || queryer.args[2] != "project-123" || queryer.args[3] != "req-export" {
		t.Fatalf("audit lost core context: %#v", queryer.args)
	}
	metadata, _ := queryer.args[4].(string)
	for _, expected := range []string{`"trace_id":"trace-1"`, `"include_full":true`, `"event_count":3`} {
		if !strings.Contains(metadata, expected) {
			t.Fatalf("audit metadata missing %s: %s", expected, metadata)
		}
	}
}

func TestDisabledExportAuditorFailsExplicitly(t *testing.T) {
	auditor := NewDisabledExportAuditor()

	err := auditor.RecordExport(context.Background(), ExportAuditInput{
		TenantID:  "tenant-123",
		ProjectID: "project-123",
		TraceID:   "trace-1",
	})

	if code := ErrorCode(err); code != "TRACE_AUDIT_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected audit backend error, got %s (%v)", code, err)
	}
}

type recordingTraceQueryer struct {
	query         string
	args          []any
	rows          *fakeTraceRows
	err           error
	writeTenantID string
}

func (q *recordingTraceQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
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

func (q *recordingTraceQueryer) QueryTenantWriteContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.writeTenantID = tenantID
	return q.QueryContext(ctx, query, args...)
}

type fakeTraceRows struct {
	values [][]any
	index  int
	err    error
}

func (r *fakeTraceRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeTraceRows) Scan(dest ...any) error {
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
		default:
			return errors.New("unsupported scan target")
		}
	}
	return nil
}

func (r *fakeTraceRows) Close() error {
	return nil
}

func (r *fakeTraceRows) Err() error {
	return r.err
}
