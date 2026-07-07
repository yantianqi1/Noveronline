package workflows

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLWorkflowEventReaderListsEventsAfterCursorAndSanitizesPayload(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				true,
				"evt-2",
				"run-1",
				"project-1",
				2,
				"stage_progress",
				`{"stage":"parse","credential_ref":"cred-1","nested":{"api_key":"secret","safe":"kept"}}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLWorkflowEventReader(SQLWorkflowEventReaderConfig{Queryer: queryer, Limit: 25})

	records, err := reader.ListWorkflowEvents(context.Background(), ListWorkflowEventsInput{
		TenantID:     "tenant-1",
		RunID:        "run-1",
		AfterEventID: "evt-1",
	})

	if err != nil {
		t.Fatalf("list workflow events: %v", err)
	}
	if len(records) != 1 || records[0].EventID != "evt-2" || records[0].Payload["stage"] != "parse" {
		t.Fatalf("unexpected records: %#v", records)
	}
	if _, ok := records[0].Payload["credential_ref"]; ok {
		t.Fatalf("workflow event leaked credential ref: %#v", records[0].Payload)
	}
	nested, ok := records[0].Payload["nested"].(map[string]any)
	if !ok || nested["safe"] != "kept" {
		t.Fatalf("expected nested safe payload to remain, got %#v", records[0].Payload)
	}
	if _, ok := nested["api_key"]; ok {
		t.Fatalf("workflow event leaked nested api key: %#v", records[0].Payload)
	}
	if !strings.Contains(queryer.query, "FROM workflow_events") || !strings.Contains(queryer.query, "after_cursor") {
		t.Fatalf("expected workflow event resume query, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "run-1", "evt-1", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLWorkflowEventReaderRejectsMissingCursor(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				false,
				nil,
				nil,
				nil,
				nil,
				nil,
				nil,
				nil,
			}},
		},
	}
	reader := NewSQLWorkflowEventReader(SQLWorkflowEventReaderConfig{Queryer: queryer})

	_, err := reader.ListWorkflowEvents(context.Background(), ListWorkflowEventsInput{
		TenantID:     "tenant-1",
		RunID:        "run-1",
		AfterEventID: "evt-missing",
	})

	if code := ErrorCode(err); code != "EVENT_CURSOR_NOT_FOUND" {
		t.Fatalf("expected missing cursor, got %s (%v)", code, err)
	}
}

func TestSQLWorkflowEventReaderUsesTenantContextQueryer(t *testing.T) {
	queryer := &recordingTenantWorkflowEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				true,
				"evt-1",
				"run-1",
				"project-1",
				1,
				"seed.stage.pending",
				`{"stage":"parse_file"}`,
				"2026-07-04T00:00:00Z",
			}},
		},
	}
	reader := NewSQLWorkflowEventReader(SQLWorkflowEventReaderConfig{Queryer: queryer, Limit: 25})

	records, err := reader.ListWorkflowEvents(context.Background(), ListWorkflowEventsInput{
		TenantID:     "tenant-1",
		RunID:        "run-1",
		AfterEventID: "",
	})

	if err != nil {
		t.Fatalf("list workflow events: %v", err)
	}
	if len(records) != 1 || records[0].EventID != "evt-1" {
		t.Fatalf("unexpected workflow events: %#v", records)
	}
	if queryer.tenantID != "tenant-1" || queryer.query == "" {
		t.Fatalf("workflow event reader did not use tenant context queryer: %#v", queryer)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "run-1", "", 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLWorkflowEventReaderSanitizesUnexpectedQueryErrors(t *testing.T) {
	sensitiveErr := errors.New("driver leaked prompt=hidden api_key=sk-hidden credential_ref=cred-1 object_key=projects/private raw_text=secret")
	tests := []struct {
		name    string
		queryer WriterEventSQLQueryer
	}{
		{
			name:    "query error",
			queryer: &recordingWriterEventQueryer{err: sensitiveErr},
		},
		{
			name:    "rows error",
			queryer: &recordingWriterEventQueryer{rows: &fakeWriterEventRows{err: sensitiveErr}},
		},
		{
			name: "scan error",
			queryer: &recordingWriterEventQueryer{
				rows: &fakeWriterEventRows{
					values:  [][]any{{}},
					scanErr: sensitiveErr,
				},
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			reader := NewSQLWorkflowEventReader(SQLWorkflowEventReaderConfig{Queryer: test.queryer})

			_, err := reader.ListWorkflowEvents(context.Background(), ListWorkflowEventsInput{
				TenantID: "tenant-1",
				RunID:    "run-1",
			})

			if code := ErrorCode(err); code != "WORKFLOW_EVENT_QUERY_FAILED" {
				t.Fatalf("expected stable workflow event query code, got %s (%v)", code, err)
			}
			assertWorkflowEventReaderErrorSanitized(t, err)
		})
	}
}

func assertWorkflowEventReaderErrorSanitized(t *testing.T, err error) {
	t.Helper()
	if err == nil {
		t.Fatal("expected error")
	}
	message := err.Error()
	if message != "workflow event query failed" {
		t.Fatalf("expected stable public message, got %q", message)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "raw_text", "secret"} {
		if strings.Contains(message, forbidden) {
			t.Fatalf("workflow event reader error leaked %q: %s", forbidden, message)
		}
	}
}

type recordingTenantWorkflowEventQueryer struct {
	tenantID string
	query    string
	args     []any
	rows     *fakeWriterEventRows
	err      error
}

func (q *recordingTenantWorkflowEventQueryer) QueryContext(context.Context, string, ...any) (WriterEventSQLRows, error) {
	return nil, errors.New("plain QueryContext should not be used for workflow event reader")
}

func (q *recordingTenantWorkflowEventQueryer) QueryTenantContext(_ context.Context, tenantID string, query string, args ...any) (WriterEventSQLRows, error) {
	q.tenantID = tenantID
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
