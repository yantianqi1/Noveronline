package workflows

import (
	"context"
	"reflect"
	"strings"
	"testing"
)

func TestSQLWorkflowReaderReadsPersistedWorkflowRunWithinTenant(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"run-1",
				"seed_run",
				"project-1",
				"running",
				42,
				"reading chapter 2",
				"",
				"",
				"2026-07-04T01:00:00Z",
				"2026-07-04T01:02:00Z",
			}},
		},
	}
	reader := NewSQLWorkflowReader(SQLWorkflowReaderConfig{Queryer: queryer})

	run, err := reader.GetWorkflowRun(context.Background(), GetWorkflowRunInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if err != nil {
		t.Fatalf("get workflow run: %v", err)
	}
	if run.RunID != "run-1" || run.WorkflowType != "seed_run" || run.ProjectID != "project-1" || run.Status != "running" {
		t.Fatalf("unexpected run: %#v", run)
	}
	if run.Progress != 42 || run.Message != "reading chapter 2" || run.CreatedAt == "" || run.UpdatedAt == "" {
		t.Fatalf("unexpected workflow metadata: %#v", run)
	}
	if !strings.Contains(queryer.query, "FROM workflow_runs") {
		t.Fatalf("expected workflow_runs query, got %s", queryer.query)
	}
	if strings.Contains(queryer.query, "result_jsonb") || strings.Contains(queryer.query, "options_jsonb") || strings.Contains(queryer.query, "credential_ref") {
		t.Fatalf("workflow reader selected sensitive payload fields: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "run-1"}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLWorkflowReaderReturnsNotFoundForMissingRun(t *testing.T) {
	queryer := &recordingWriterEventQueryer{rows: &fakeWriterEventRows{}}
	reader := NewSQLWorkflowReader(SQLWorkflowReaderConfig{Queryer: queryer})

	_, err := reader.GetWorkflowRun(context.Background(), GetWorkflowRunInput{
		TenantID: "tenant-1",
		RunID:    "run-missing",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected not found, got %s (%v)", code, err)
	}
}
