package workflows

import (
	"context"
	"errors"
	"strings"
	"testing"

	"go.temporal.io/sdk/client"
)

func TestTemporalWorkflowCancellerCancelsStoredTemporalWorkflowAndPersistsStatus(t *testing.T) {
	client := &recordingWorkflowTemporalClient{}
	store := &recordingWorkflowCancellationStore{
		target: WorkflowCancellationTarget{
			RunID:              "run-1",
			ProjectID:          "project-1",
			WorkflowType:       "seed_run",
			TemporalWorkflowID: "seed_run_run-1",
		},
	}
	canceller := NewTemporalWorkflowCanceller(TemporalWorkflowCancellerConfig{
		Client: client,
		Store:  store,
	})

	cancelled, err := canceller.CancelWorkflowRun(context.Background(), CancelWorkflowRunInput{
		TenantID:    "tenant-1",
		RunID:       "run-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
	})

	if err != nil {
		t.Fatalf("cancel workflow run: %v", err)
	}
	if client.cancelledWorkflowID != "seed_run_run-1" || client.cancelledRunID != "" {
		t.Fatalf("unexpected temporal cancellation target: %#v", client)
	}
	if store.targetInput.TenantID != "tenant-1" || store.targetInput.RunID != "run-1" {
		t.Fatalf("store lost target context: %#v", store.targetInput)
	}
	if store.cancelInput.TenantID != "tenant-1" || store.cancelInput.RunID != "run-1" || store.cancelInput.ProjectID != "project-1" || store.cancelInput.WorkflowType != "seed_run" {
		t.Fatalf("store lost cancellation metadata: %#v", store.cancelInput)
	}
	if store.cancelInput.ActorUserID != "user-1" || store.cancelInput.RequestID != "req-1" || store.cancelInput.Status != "cancelled" {
		t.Fatalf("store lost actor/request/status metadata: %#v", store.cancelInput)
	}
	if cancelled.RunID != "run-1" || cancelled.Status != "cancelled" {
		t.Fatalf("unexpected cancellation response: %#v", cancelled)
	}
}

func TestTemporalWorkflowCancellerFailsClosedWithoutTemporalWorkflowID(t *testing.T) {
	client := &recordingWorkflowTemporalClient{}
	store := &recordingWorkflowCancellationStore{
		target: WorkflowCancellationTarget{
			RunID:        "run-1",
			ProjectID:    "project-1",
			WorkflowType: "seed_run",
		},
	}
	canceller := NewTemporalWorkflowCanceller(TemporalWorkflowCancellerConfig{
		Client: client,
		Store:  store,
	})

	_, err := canceller.CancelWorkflowRun(context.Background(), CancelWorkflowRunInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_CANCEL_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected missing backend target, got %s (%v)", code, err)
	}
	if client.cancelledWorkflowID != "" {
		t.Fatalf("temporal cancellation should not run without workflow id: %#v", client)
	}
}

func TestSQLWorkflowCancellationStoreReadsCancellationTarget(t *testing.T) {
	queryer := &recordingWriterEventQueryer{
		rows: &fakeWriterEventRows{
			values: [][]any{{
				"run-1",
				"project-1",
				"seed_run",
				"seed_run_run-1",
			}},
		},
	}
	store := NewSQLWorkflowCancellationStore(SQLWorkflowCancellationStoreConfig{Queryer: queryer})

	target, err := store.GetWorkflowCancellationTarget(context.Background(), WorkflowCancellationTargetInput{
		TenantID: "tenant-1",
		RunID:    "run-1",
	})

	if err != nil {
		t.Fatalf("get workflow cancellation target: %v", err)
	}
	if target.RunID != "run-1" || target.ProjectID != "project-1" || target.WorkflowType != "seed_run" || target.TemporalWorkflowID != "seed_run_run-1" {
		t.Fatalf("unexpected cancellation target: %#v", target)
	}
	if !strings.Contains(queryer.query, "FROM workflow_runs") || strings.Contains(queryer.query, "result_jsonb") {
		t.Fatalf("expected sanitized workflow_runs target query, got %s", queryer.query)
	}
}

func TestSQLWorkflowCancellationStorePersistsCancelledStatusAndWorkflowEvent(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLWorkflowCancellationStore(SQLWorkflowCancellationStoreConfig{Execer: execer})

	err := store.CancelWorkflowRun(context.Background(), WorkflowCancellationInput{
		TenantID:     "11111111-1111-4111-8111-111111111111",
		ProjectID:    "22222222-2222-4222-8222-222222222222",
		RunID:        "33333333-3333-4333-8333-333333333333",
		WorkflowType: "seed_run",
		ActorUserID:  "44444444-4444-4444-8444-444444444444",
		RequestID:    "req-cancel",
		Status:       "cancelled",
	})

	if err != nil {
		t.Fatalf("persist workflow cancellation: %v", err)
	}
	if !strings.Contains(execer.query, "UPDATE workflow_runs") || strings.Contains(execer.query, "UPDATE writer_runs") {
		t.Fatalf("expected generic workflow run status update only, got %s", execer.query)
	}
	if !strings.Contains(execer.query, "workflow.cancelled") || !strings.Contains(execer.query, "workflow_events") {
		t.Fatalf("expected cancelled workflow event insert, got %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	if strings.Contains(joinedArgs, "credential_ref") || strings.Contains(joinedArgs, "api_key") || strings.Contains(joinedArgs, "encrypted_api_key") {
		t.Fatalf("cancellation SQL args leaked credential material: %s", joinedArgs)
	}
	if !strings.Contains(joinedArgs, "req-cancel") || !strings.Contains(joinedArgs, "cancelled") || !strings.Contains(joinedArgs, "seed_run") {
		t.Fatalf("expected request/status/workflow metadata in cancellation args, got %s", joinedArgs)
	}
}

type recordingWorkflowCancellationStore struct {
	target      WorkflowCancellationTarget
	targetErr   error
	cancelErr   error
	targetInput WorkflowCancellationTargetInput
	cancelInput WorkflowCancellationInput
}

func (s *recordingWorkflowCancellationStore) GetWorkflowCancellationTarget(_ context.Context, input WorkflowCancellationTargetInput) (WorkflowCancellationTarget, error) {
	s.targetInput = input
	if s.targetErr != nil {
		return WorkflowCancellationTarget{}, s.targetErr
	}
	return s.target, nil
}

func (s *recordingWorkflowCancellationStore) CancelWorkflowRun(_ context.Context, input WorkflowCancellationInput) error {
	s.cancelInput = input
	return s.cancelErr
}

type recordingWorkflowTemporalClient struct {
	cancelledWorkflowID string
	cancelledRunID      string
	err                 error
}

func (c *recordingWorkflowTemporalClient) ExecuteWorkflow(context.Context, client.StartWorkflowOptions, any, ...any) (client.WorkflowRun, error) {
	return nil, errors.New("not used")
}

func (c *recordingWorkflowTemporalClient) CancelWorkflow(_ context.Context, workflowID string, runID string) error {
	c.cancelledWorkflowID = workflowID
	c.cancelledRunID = runID
	return c.err
}
