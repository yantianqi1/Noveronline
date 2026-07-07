package workflows

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSQLSeedRunReaderListsSeedRunsWithinTenantProject(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"seed-run-1",
				SeedWorkflowType,
				"project-1",
				"running",
				15,
				"parse_file pending",
				"",
				"",
				"2026-07-04T01:00:00Z",
				"2026-07-04T01:02:00Z",
			}},
		},
	}
	reader := NewSQLSeedRunReader(SQLSeedRunReaderConfig{Queryer: queryer, Limit: 25})

	runs, err := reader.ListSeedRuns(context.Background(), ListSeedRunsInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if err != nil {
		t.Fatalf("list seed runs: %v", err)
	}
	if len(runs) != 1 || runs[0].RunID != "seed-run-1" || runs[0].WorkflowType != SeedWorkflowType {
		t.Fatalf("unexpected seed runs: %#v", runs)
	}
	if !strings.Contains(queryer.query, "workflow_type = $3") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("expected tenant/project/seed filter query, got %s", queryer.query)
	}
	if strings.Contains(queryer.query, "result_jsonb") || strings.Contains(queryer.query, "options_jsonb") || strings.Contains(queryer.query, "credential_ref") {
		t.Fatalf("seed reader selected sensitive payload fields: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "project-1", SeedWorkflowType, 25}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLSeedRunReaderGetsOnlySeedWorkflowRuns(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"seed-run-1",
				SeedWorkflowType,
				"project-1",
				"queued",
				0,
				"",
				"",
				"",
				"2026-07-04T01:00:00Z",
				"2026-07-04T01:00:00Z",
			}},
		},
	}
	reader := NewSQLSeedRunReader(SQLSeedRunReaderConfig{Queryer: queryer})

	run, err := reader.GetSeedRun(context.Background(), GetSeedRunInput{
		TenantID: "tenant-1",
		RunID:    "seed-run-1",
	})

	if err != nil {
		t.Fatalf("get seed run: %v", err)
	}
	if run.RunID != "seed-run-1" || run.WorkflowType != SeedWorkflowType {
		t.Fatalf("unexpected seed run: %#v", run)
	}
	if !strings.Contains(queryer.query, "workflow_type = $3") {
		t.Fatalf("expected seed workflow type guard, got %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "seed-run-1", SeedWorkflowType}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLSeedRunReaderUsesTenantContextQueryerForListAndGet(t *testing.T) {
	listQueryer := &recordingTenantSeedRunQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"seed-run-1",
				SeedWorkflowType,
				"project-1",
				"running",
				15,
				"parse_file pending",
				"",
				"",
				"2026-07-04T01:00:00Z",
				"2026-07-04T01:02:00Z",
			}},
		},
	}
	reader := NewSQLSeedRunReader(SQLSeedRunReaderConfig{Queryer: listQueryer, Limit: 25})

	if _, err := reader.ListSeedRuns(context.Background(), ListSeedRunsInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	}); err != nil {
		t.Fatalf("list seed runs: %v", err)
	}
	if listQueryer.tenantID != "tenant-1" || listQueryer.query == "" {
		t.Fatalf("seed run list did not use tenant context queryer: %#v", listQueryer)
	}
	if !reflect.DeepEqual(listQueryer.args, []any{"tenant-1", "project-1", SeedWorkflowType, 25}) {
		t.Fatalf("unexpected list query args: %#v", listQueryer.args)
	}

	getQueryer := &recordingTenantSeedRunQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"seed-run-1",
				SeedWorkflowType,
				"project-1",
				"queued",
				0,
				"",
				"",
				"",
				"2026-07-04T01:00:00Z",
				"2026-07-04T01:00:00Z",
			}},
		},
	}
	reader = NewSQLSeedRunReader(SQLSeedRunReaderConfig{Queryer: getQueryer})

	if _, err := reader.GetSeedRun(context.Background(), GetSeedRunInput{
		TenantID: "tenant-1",
		RunID:    "seed-run-1",
	}); err != nil {
		t.Fatalf("get seed run: %v", err)
	}
	if getQueryer.tenantID != "tenant-1" || getQueryer.query == "" {
		t.Fatalf("seed run detail did not use tenant context queryer: %#v", getQueryer)
	}
	if !reflect.DeepEqual(getQueryer.args, []any{"tenant-1", "seed-run-1", SeedWorkflowType}) {
		t.Fatalf("unexpected get query args: %#v", getQueryer.args)
	}
}

func TestSQLSeedRunReaderSanitizesUnexpectedQueryErrors(t *testing.T) {
	sensitiveErr := errors.New("driver leaked prompt=hidden api_key=sk-hidden credential_ref=cred-1 object_key=projects/private raw_text=secret")
	tests := []struct {
		name string
		run  func(*SQLSeedRunReader) error
	}{
		{
			name: "list query error",
			run: func(reader *SQLSeedRunReader) error {
				_, err := reader.ListSeedRuns(context.Background(), ListSeedRunsInput{TenantID: "tenant-1", ProjectID: "project-1"})
				return err
			},
		},
		{
			name: "get query error",
			run: func(reader *SQLSeedRunReader) error {
				_, err := reader.GetSeedRun(context.Background(), GetSeedRunInput{TenantID: "tenant-1", RunID: "seed-run-1"})
				return err
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			reader := NewSQLSeedRunReader(SQLSeedRunReaderConfig{
				Queryer: &recordingWriterEventQueryer{err: sensitiveErr},
			})

			err := test.run(reader)

			if code := ErrorCode(err); code != "WORKFLOW_QUERY_FAILED" {
				t.Fatalf("expected stable query failure code, got %s (%v)", code, err)
			}
			assertSeedRunReaderErrorSanitized(t, err)
		})
	}

	t.Run("rows error", func(t *testing.T) {
		reader := NewSQLSeedRunReader(SQLSeedRunReaderConfig{
			Queryer: &recordingWriterEventQueryer{rows: &fakeWriterEventRows{err: sensitiveErr}},
		})

		_, err := reader.ListSeedRuns(context.Background(), ListSeedRunsInput{TenantID: "tenant-1", ProjectID: "project-1"})

		if code := ErrorCode(err); code != "WORKFLOW_QUERY_FAILED" {
			t.Fatalf("expected stable rows failure code, got %s (%v)", code, err)
		}
		assertSeedRunReaderErrorSanitized(t, err)
	})

	t.Run("scan error", func(t *testing.T) {
		reader := NewSQLSeedRunReader(SQLSeedRunReaderConfig{
			Queryer: &recordingWriterEventQueryer{
				rows: &fakeWriterEventRows{
					values:  [][]any{{}},
					scanErr: sensitiveErr,
				},
			},
		})

		_, err := reader.ListSeedRuns(context.Background(), ListSeedRunsInput{TenantID: "tenant-1", ProjectID: "project-1"})

		if code := ErrorCode(err); code != "WORKFLOW_QUERY_FAILED" {
			t.Fatalf("expected stable scan failure code, got %s (%v)", code, err)
		}
		assertSeedRunReaderErrorSanitized(t, err)
	})
}

func TestDisabledSeedRunReaderFailsClosed(t *testing.T) {
	reader := NewDisabledSeedRunReader()

	_, err := reader.ListSeedRuns(context.Background(), ListSeedRunsInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})
	if code := ErrorCode(err); code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected unconfigured list error, got %s (%v)", code, err)
	}

	_, err = reader.GetSeedRun(context.Background(), GetSeedRunInput{
		TenantID: "tenant-1",
		RunID:    "seed-run-1",
	})
	if code := ErrorCode(err); code != "WORKFLOW_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected unconfigured get error, got %s (%v)", code, err)
	}
}

func assertSeedRunReaderErrorSanitized(t *testing.T, err error) {
	t.Helper()
	if err == nil {
		t.Fatal("expected error")
	}
	message := err.Error()
	if message != "seed run query failed" {
		t.Fatalf("expected stable public message, got %q", message)
	}
	for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "raw_text", "secret"} {
		if strings.Contains(message, forbidden) {
			t.Fatalf("seed run reader error leaked %q: %s", forbidden, message)
		}
	}
}

type recordingTenantSeedRunQueryer struct {
	tenantID string
	query    string
	args     []any
	rows     *fakeWriterEventRows
	err      error
}

func (q *recordingTenantSeedRunQueryer) QueryContext(context.Context, string, ...any) (WriterEventSQLRows, error) {
	return nil, errors.New("plain QueryContext should not be used for seed run reader")
}

func (q *recordingTenantSeedRunQueryer) QueryTenantContext(_ context.Context, tenantID string, query string, args ...any) (WriterEventSQLRows, error) {
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
