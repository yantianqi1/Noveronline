package worldline

import (
	"context"
	"errors"
	"reflect"
	"testing"
)

type recordingGoalStartAdmissionStore struct {
	input              StartGoalStartInput
	admission          GoalStartAdmission
	record             GoalStartRecord
	replayed           bool
	admitErr           error
	compensationInput  StartGoalStartInput
	compensationRecord GoalStartRecord
	compensationEvent  string
	compensationErr    error
	admitCalls         int
	compensationCalls  int
}

func (s *recordingGoalStartAdmissionStore) AdmitGoalStart(
	_ context.Context,
	input StartGoalStartInput,
	admission GoalStartAdmission,
) (GoalStartRecord, bool, error) {
	s.admitCalls++
	s.input = input
	s.admission = admission
	if s.admitErr != nil {
		return GoalStartRecord{}, false, s.admitErr
	}
	if s.record.RunID == "" {
		s.record = admission.Record
	}
	return s.record, s.replayed, nil
}

func (s *recordingGoalStartAdmissionStore) CompensateGoalStartStart(
	_ context.Context,
	input StartGoalStartInput,
	record GoalStartRecord,
	eventID string,
) error {
	s.compensationCalls++
	s.compensationInput = input
	s.compensationRecord = record
	s.compensationEvent = eventID
	return s.compensationErr
}

func TestSQLGoalStartStarterPersistsGoalAndStartsTemporal(t *testing.T) {
	store := &recordingGoalStartAdmissionStore{}
	temporalClient := &recordingWorldlineTemporalClient{}
	starter := NewSQLGoalStartStarter(SQLGoalStartStarterConfig{
		Store: store,
		NewID: fixedWorldlineIDs(
			"00000000-0000-4000-8000-000000000201",
			"00000000-0000-4000-8000-000000000202",
		),
		Client:    temporalClient,
		TaskQueue: "worldline-cast-test",
	})
	input := StartGoalStartInput{
		TenantID:     "00000000-0000-4000-8000-000000000001",
		ProjectID:    "00000000-0000-4000-8000-000000000002",
		ActorUserID:  "00000000-0000-4000-8000-000000000003",
		RequestID:    "req-goal-start-1",
		Goal:         "  探索主角与反派的初次对峙  ",
		AnchorPathID: "",
		Options:      map[string]any{"source": "worldline_shell", "prompt": "private"},
	}

	record, err := starter.StartGoalStart(context.Background(), input)
	if err != nil {
		t.Fatalf("start goal-start: %v", err)
	}
	if record.RunID != "00000000-0000-4000-8000-000000000201" ||
		record.WorkflowType != WorldlineGoalStartWorkflowType || record.Status != "queued" {
		t.Fatalf("unexpected goal-start record: %#v", record)
	}
	if store.admitCalls != 1 || store.input.Goal != "探索主角与反派的初次对峙" {
		t.Fatalf("goal-start admission lost normalized context: %#v", store.input)
	}
	if store.input.Options["prompt"] != nil {
		t.Fatalf("goal-start options retained prompt: %#v", store.input.Options)
	}
	if temporalClient.options.ID != "worldline_goal_start_00000000-0000-4000-8000-000000000201" ||
		temporalClient.options.TaskQueue != "worldline-cast-test" ||
		temporalClient.workflow != PiWorldlineGoalStartWorkflow {
		t.Fatalf("unexpected Temporal start: options=%#v workflow=%#v", temporalClient.options, temporalClient.workflow)
	}
	if len(temporalClient.args) != 1 {
		t.Fatalf("expected one Temporal payload, got %#v", temporalClient.args)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok || payload["goal"] != "探索主角与反派的初次对峙" || payload["run_id"] != record.RunID {
		t.Fatalf("unexpected temporal payload: %#v", temporalClient.args)
	}
}

func TestSQLGoalStartStarterReplaysWithoutRestartingTemporal(t *testing.T) {
	store := &recordingGoalStartAdmissionStore{
		replayed: true,
		record: GoalStartRecord{
			RunID:        "00000000-0000-4000-8000-000000000301",
			ProjectID:    "00000000-0000-4000-8000-000000000002",
			WorkflowType: WorldlineGoalStartWorkflowType,
			Status:       "ready",
			Goal:         "replayed",
			SessionID:    "00000000-0000-4000-8000-000000000302",
		},
	}
	temporalClient := &recordingWorldlineTemporalClient{}
	starter := NewSQLGoalStartStarter(SQLGoalStartStarterConfig{
		Store:     store,
		NewID:     fixedWorldlineIDs("00000000-0000-4000-8000-000000000303"),
		Client:    temporalClient,
		TaskQueue: "worldline-cast-test",
	})

	record, err := starter.StartGoalStart(context.Background(), StartGoalStartInput{
		TenantID:    "00000000-0000-4000-8000-000000000001",
		ProjectID:   "00000000-0000-4000-8000-000000000002",
		ActorUserID: "00000000-0000-4000-8000-000000000003",
		RequestID:   "req-goal-start-replay",
		Goal:        "replayed",
	})
	if err != nil {
		t.Fatalf("replay goal-start: %v", err)
	}
	if record.SessionID != "00000000-0000-4000-8000-000000000302" {
		t.Fatalf("unexpected replayed record: %#v", record)
	}
	if temporalClient.workflow != nil {
		t.Fatalf("replay restarted temporal: %#v", temporalClient)
	}
}

func TestSQLGoalStartStarterCompensatesWhenTemporalFails(t *testing.T) {
	store := &recordingGoalStartAdmissionStore{}
	temporalClient := &recordingWorldlineTemporalClient{err: errors.New("private Temporal SDK detail")}
	starter := NewSQLGoalStartStarter(SQLGoalStartStarterConfig{
		Store: store,
		NewID: fixedWorldlineIDs(
			"00000000-0000-4000-8000-000000000401",
			"00000000-0000-4000-8000-000000000402",
		),
		Client:    temporalClient,
		TaskQueue: "worldline-cast-test",
	})

	_, err := starter.StartGoalStart(context.Background(), StartGoalStartInput{
		TenantID:    "00000000-0000-4000-8000-000000000001",
		ProjectID:   "00000000-0000-4000-8000-000000000002",
		ActorUserID: "00000000-0000-4000-8000-000000000003",
		RequestID:   "req-goal-start-fail",
		Goal:        "should fail closed",
	})
	if code := ErrorCode(err); code != "WORKFLOW_FAILED" {
		t.Fatalf("expected WORKFLOW_FAILED, got %s (%v)", code, err)
	}
	if store.compensationCalls != 1 {
		t.Fatalf("expected compensation, got %#v", store)
	}
}

func TestValidateGoalStartInputRequiresGoal(t *testing.T) {
	err := validateGoalStartInput(StartGoalStartInput{
		TenantID:    "t",
		ProjectID:   "p",
		ActorUserID: "a",
		RequestID:   "r",
	})
	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected validation, got %s (%v)", code, err)
	}
}

func TestGoalStartTemporalPayloadShape(t *testing.T) {
	payload := goalStartTemporalPayload(StartGoalStartInput{
		TenantID:    "t1",
		ActorUserID: "u1",
		RequestID:   "r1",
		Goal:        "goal",
	}, GoalStartRecord{
		RunID:     "run1",
		ProjectID: "p1",
	}, "trace1")
	want := map[string]any{
		"tenant_id":      "t1",
		"project_id":     "p1",
		"run_id":         "run1",
		"workflow_type":  WorldlineGoalStartWorkflowType,
		"requested_by":   "u1",
		"request_id":     "r1",
		"trace_id":       "trace1",
		"goal":           "goal",
		"anchor_path_id": "",
		"options": map[string]any{
			"module_key":           WorldlineCastPlannerModuleKey,
			"required_module_keys": []string{WorldlineCastPlannerModuleKey},
		},
	}
	if !reflect.DeepEqual(payload, want) {
		t.Fatalf("payload mismatch:\n got %#v\nwant %#v", payload, want)
	}
}
