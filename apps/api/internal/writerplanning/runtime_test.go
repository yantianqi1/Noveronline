package writerplanning

import (
	"context"
	"errors"
	"testing"

	"go.temporal.io/sdk/client"
)

func TestTemporalStarterUsesDedicatedModulesAndPrivateIDOnlyPayloads(t *testing.T) {
	tests := []struct {
		name, kind, workflow, module string
		input                        StartInput
	}{
		{"dedup", KindDedup, DedupWorkflowName, DedupModuleKey, StartInput{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1", Kind: KindDedup, BlockIDs: []string{"block-1"}}},
		{"book plan", KindBookPlan, BookPlanWorkflowName, BookPlanModuleKey, StartInput{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1", Kind: KindBookPlan, BookPlanID: "plan-1", ExpectedVersion: 3}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store, temporal := &recordingAdmissionStore{}, &recordingTemporalClient{}
			result, err := NewTemporalStarter(TemporalConfig{Client: temporal, Store: store}).Start(context.Background(), test.input)
			if err != nil || result.RunID == "" || result.Status != "queued" {
				t.Fatalf("start planning: %#v %v", result, err)
			}
			if temporal.workflow != test.workflow || temporal.options.TaskQueue != PlanningTaskQueue {
				t.Fatalf("wrong handoff: %#v %q", temporal.options, temporal.workflow)
			}
			payload := temporal.args[0].(map[string]any)
			workflowContext := payload["context"].(map[string]any)
			if workflowContext["module_key"] != test.module || workflowContext["workflow_type"] != WorkflowType(test.kind) {
				t.Fatalf("wrong context: %#v", workflowContext)
			}
			if _, leaked := payload["content_text"]; leaked {
				t.Fatal("Temporal payload leaked content")
			}
		})
	}
}

func TestTemporalStarterReturnsReplayWithoutStartingAgain(t *testing.T) {
	store, temporal := &recordingAdmissionStore{replay: true}, &recordingTemporalClient{}
	result, err := NewTemporalStarter(TemporalConfig{Client: temporal, Store: store}).Start(context.Background(), StartInput{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1", Kind: KindDedup, ChapterID: "chapter-1"})
	if err != nil || !result.Replay || temporal.calls != 0 {
		t.Fatalf("replay started Temporal: %#v calls=%d err=%v", result, temporal.calls, err)
	}
}

func TestTemporalStarterCompensatesStartFailure(t *testing.T) {
	store, temporal := &recordingAdmissionStore{}, &recordingTemporalClient{err: errors.New("private temporal failure")}
	_, err := NewTemporalStarter(TemporalConfig{Client: temporal, Store: store}).Start(context.Background(), StartInput{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1", Kind: KindBookPlan, BookPlanID: "plan-1", ExpectedVersion: 1})
	if ErrorCode(err) != "WRITER_PLANNING_START_FAILED" || !store.compensated {
		t.Fatalf("not compensated: code=%s store=%#v", ErrorCode(err), store)
	}
}

func TestStartValidationRequiresExplicitSelectionAndPlanVersion(t *testing.T) {
	starter := NewTemporalStarter(TemporalConfig{Client: &recordingTemporalClient{}, Store: &recordingAdmissionStore{}})
	inputs := []StartInput{{TenantID: "t", ProjectID: "p", ActorUserID: "u", RequestID: "r", Kind: KindDedup}, {TenantID: "t", ProjectID: "p", ActorUserID: "u", RequestID: "r", Kind: KindBookPlan, BookPlanID: "plan"}}
	for _, input := range inputs {
		if _, err := starter.Start(context.Background(), input); ErrorCode(err) != "VALIDATION_FAILED" {
			t.Fatalf("invalid accepted: %#v err=%v", input, err)
		}
	}
}

type recordingAdmissionStore struct{ replay, compensated bool }

func (s *recordingAdmissionStore) Admit(_ context.Context, _ StartInput, proposed Admission, _, _ string) (Admission, bool, error) {
	if s.replay {
		proposed.Replay = true
		return proposed, true, nil
	}
	return proposed, false, nil
}
func (s *recordingAdmissionStore) Compensate(context.Context, StartInput, Admission) error {
	s.compensated = true
	return nil
}

type recordingTemporalClient struct {
	options  client.StartWorkflowOptions
	workflow any
	args     []any
	calls    int
	err      error
}

func (c *recordingTemporalClient) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.calls++
	c.options, c.workflow, c.args = options, workflow, args
	return nil, c.err
}
