package worldline

import (
	"context"
	"errors"
	"reflect"
	"testing"
)

type recordingPreparationAdmissionStore struct {
	input              CreatePreparationInput
	admission          PreparationAdmission
	record             PreparationRecord
	replayed           bool
	admitErr           error
	compensationInput  CreatePreparationInput
	compensationRecord PreparationRecord
	compensationEvent  string
	compensationErr    error
	admitCalls         int
	compensationCalls  int
}

func (s *recordingPreparationAdmissionStore) AdmitPreparation(
	_ context.Context,
	input CreatePreparationInput,
	admission PreparationAdmission,
) (PreparationRecord, bool, error) {
	s.admitCalls++
	s.input = input
	s.admission = admission
	if s.admitErr != nil {
		return PreparationRecord{}, false, s.admitErr
	}
	if s.record.RunID == "" {
		s.record = admission.Record
	}
	return s.record, s.replayed, nil
}

func (s *recordingPreparationAdmissionStore) CompensatePreparationStart(
	_ context.Context,
	input CreatePreparationInput,
	record PreparationRecord,
	eventID string,
) error {
	s.compensationCalls++
	s.compensationInput = input
	s.compensationRecord = record
	s.compensationEvent = eventID
	return s.compensationErr
}

func TestSQLPreparationStarterPersistsSelectionsAndStartsTemporal(t *testing.T) {
	store := &recordingPreparationAdmissionStore{}
	temporalClient := &recordingWorldlineTemporalClient{}
	starter := NewSQLPreparationStarter(SQLPreparationStarterConfig{
		Store: store,
		NewID: fixedWorldlineIDs(
			"00000000-0000-4000-8000-000000000101",
			"00000000-0000-4000-8000-000000000102",
			"00000000-0000-4000-8000-000000000103",
		),
		Client:    temporalClient,
		TaskQueue: "worldline-prepare-test",
	})
	input := CreatePreparationInput{
		TenantID:    "00000000-0000-4000-8000-000000000001",
		ProjectID:   "00000000-0000-4000-8000-000000000002",
		ActorUserID: "00000000-0000-4000-8000-000000000003",
		RequestID:   "req-prepare-1",
		Goal:        "  Prepare the council  ",
		AgentRefs: []PreparationAgentRef{
			{SourceKind: " Entity ", SourceID: "00000000-0000-4000-8000-000000000011"},
			{SourceKind: "entity", SourceID: "00000000-0000-4000-8000-000000000011"},
		},
		SourceRefs: []PreparationSourceRef{
			{SourceKind: "event", SourceID: "00000000-0000-4000-8000-000000000012"},
		},
		Options: map[string]any{
			"pace":       "steady",
			"prompt":     "private",
			"branch_id":  "legacy",
			"nested":     map[string]any{"credential_ref": "secret", "focus": "relationships"},
			"agent_refs": []any{map[string]any{"source_kind": "asset", "source_id": "untrusted"}},
		},
	}

	record, err := starter.StartPreparation(context.Background(), input)
	if err != nil {
		t.Fatalf("start preparation: %v", err)
	}
	if record.RunID != "00000000-0000-4000-8000-000000000101" ||
		record.PrepareID != "00000000-0000-4000-8000-000000000102" ||
		record.WorkflowType != WorldlinePreparationWorkflowType || record.Status != "queued" {
		t.Fatalf("unexpected preparation record: %#v", record)
	}
	if store.admitCalls != 1 || store.input.Goal != "Prepare the council" {
		t.Fatalf("preparation admission lost normalized context: %#v", store.input)
	}
	if len(store.input.AgentRefs) != 1 || store.input.AgentRefs[0].SourceKind != "entity" ||
		len(store.input.SourceRefs) != 1 || store.input.SourceRefs[0].SourceKind != "worldline_event" {
		t.Fatalf("preparation refs were not normalized: agents=%#v sources=%#v", store.input.AgentRefs, store.input.SourceRefs)
	}
	if _, exists := store.input.Options["prompt"]; exists {
		t.Fatalf("preparation options retained prompt: %#v", store.input.Options)
	}
	if _, exists := store.input.Options["branch_id"]; exists {
		t.Fatalf("preparation options retained branch semantics: %#v", store.input.Options)
	}
	nested, _ := store.input.Options["nested"].(map[string]any)
	if nested["focus"] != "relationships" {
		t.Fatalf("preparation options lost public nested data: %#v", store.input.Options)
	}
	if _, exists := nested["credential_ref"]; exists {
		t.Fatalf("preparation options retained nested credential: %#v", store.input.Options)
	}
	wantAgentRefs := []map[string]string{{
		"source_kind": "entity", "source_id": "00000000-0000-4000-8000-000000000011",
	}}
	if !reflect.DeepEqual(store.input.Options["agent_refs"], wantAgentRefs) {
		t.Fatalf("preparation options did not persist trusted agent refs: %#v", store.input.Options)
	}
	if temporalClient.options.ID != "worldline_preparation_00000000-0000-4000-8000-000000000101" ||
		temporalClient.options.TaskQueue != "worldline-prepare-test" || temporalClient.workflow != worldlinePreparationWorkflow {
		t.Fatalf("unexpected Temporal start: options=%#v workflow=%#v", temporalClient.options, temporalClient.workflow)
	}
	if len(temporalClient.args) != 1 {
		t.Fatalf("expected one Temporal payload, got %#v", temporalClient.args)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok || payload["prepare_id"] != record.PrepareID || payload["request_id"] != "req-prepare-1" {
		t.Fatalf("unexpected preparation Temporal payload: %#v", temporalClient.args)
	}
	contextPayload, _ := payload["context"].(map[string]any)
	if contextPayload["workflow_type"] != WorldlinePreparationWorkflowType ||
		contextPayload["module_key"] != WorldlinePreparationModuleKey ||
		contextPayload["actor_user_id"] != input.ActorUserID {
		t.Fatalf("Temporal preparation context lost scope: %#v", contextPayload)
	}
	for _, forbidden := range []string{"prompt", "credential_ref", "branch_id", "private"} {
		if containsJSONKeyOrValue(payload, forbidden) {
			t.Fatalf("Temporal preparation payload leaked %q: %#v", forbidden, payload)
		}
	}
}

func TestSQLPreparationStarterReplaysWithoutSecondTemporalStart(t *testing.T) {
	store := &recordingPreparationAdmissionStore{
		replayed: true,
		record: PreparationRecord{
			RunID: "existing-run", PrepareID: "existing-prepare", ProjectID: "project",
			WorkflowType: WorldlinePreparationWorkflowType, Status: "completed", Lifecycle: "ready",
		},
	}
	temporalClient := &recordingWorldlineTemporalClient{}
	starter := NewSQLPreparationStarter(SQLPreparationStarterConfig{
		Store: store, Client: temporalClient,
		NewID: fixedWorldlineIDs(
			"00000000-0000-4000-8000-000000000101",
			"00000000-0000-4000-8000-000000000102",
			"00000000-0000-4000-8000-000000000103",
		),
	})

	record, err := starter.StartPreparation(context.Background(), validPreparationInput())
	if err != nil {
		t.Fatalf("replay preparation: %v", err)
	}
	if record.RunID != "existing-run" || temporalClient.workflow != nil || store.compensationCalls != 0 {
		t.Fatalf("replay started duplicate side effects: record=%#v workflow=%#v compensation=%d", record, temporalClient.workflow, store.compensationCalls)
	}
}

func TestSQLPreparationStarterCompensatesTemporalStartFailure(t *testing.T) {
	store := &recordingPreparationAdmissionStore{}
	temporalClient := &recordingWorldlineTemporalClient{err: errors.New("private Temporal SDK detail")}
	starter := NewSQLPreparationStarter(SQLPreparationStarterConfig{
		Store: store, Client: temporalClient,
		NewID: fixedWorldlineIDs(
			"00000000-0000-4000-8000-000000000101",
			"00000000-0000-4000-8000-000000000102",
			"00000000-0000-4000-8000-000000000103",
			"00000000-0000-4000-8000-000000000104",
		),
	})

	_, err := starter.StartPreparation(context.Background(), validPreparationInput())
	if ErrorCode(err) != "WORKFLOW_FAILED" || err.Error() != "failed to start worldline preparation workflow" {
		t.Fatalf("unexpected sanitized Temporal failure: code=%s err=%v", ErrorCode(err), err)
	}
	if store.compensationCalls != 1 || store.compensationRecord.RunID == "" ||
		store.compensationEvent != "00000000-0000-4000-8000-000000000104" {
		t.Fatalf("preparation start failure was not compensated: %#v", store)
	}

	store.compensationErr = errors.New("private SQL error")
	_, err = starter.StartPreparation(context.Background(), validPreparationInput())
	if ErrorCode(err) != "WORKFLOW_FAILED" || err.Error() != "failed to record worldline preparation start failure" {
		t.Fatalf("unexpected compensation failure: code=%s err=%v", ErrorCode(err), err)
	}
}

func TestSQLPreparationStarterRejectsInvalidSelectionBeforeAdmission(t *testing.T) {
	for _, tt := range []struct {
		name  string
		input CreatePreparationInput
	}{
		{name: "missing agents", input: func() CreatePreparationInput {
			input := validPreparationInput()
			input.AgentRefs = nil
			return input
		}()},
		{name: "invalid agent kind", input: func() CreatePreparationInput {
			input := validPreparationInput()
			input.AgentRefs[0].SourceKind = "saved_path"
			return input
		}()},
		{name: "invalid source id", input: func() CreatePreparationInput {
			input := validPreparationInput()
			input.SourceRefs = []PreparationSourceRef{{SourceKind: "asset", SourceID: "not-a-uuid"}}
			return input
		}()},
	} {
		t.Run(tt.name, func(t *testing.T) {
			store := &recordingPreparationAdmissionStore{}
			temporalClient := &recordingWorldlineTemporalClient{}
			starter := NewSQLPreparationStarter(SQLPreparationStarterConfig{Store: store, Client: temporalClient})
			_, err := starter.StartPreparation(context.Background(), tt.input)
			if ErrorCode(err) != "VALIDATION_FAILED" {
				t.Fatalf("expected validation failure, got code=%s err=%v", ErrorCode(err), err)
			}
			if store.admitCalls != 0 || temporalClient.workflow != nil {
				t.Fatalf("invalid selection reached side effects: store=%#v temporal=%#v", store, temporalClient)
			}
		})
	}
}

func validPreparationInput() CreatePreparationInput {
	return CreatePreparationInput{
		TenantID:    "00000000-0000-4000-8000-000000000001",
		ProjectID:   "00000000-0000-4000-8000-000000000002",
		ActorUserID: "00000000-0000-4000-8000-000000000003",
		RequestID:   "req-prepare-valid",
		Goal:        "Prepare a council",
		AgentRefs: []PreparationAgentRef{{
			SourceKind: "entity", SourceID: "00000000-0000-4000-8000-000000000011",
		}},
	}
}

func containsJSONKeyOrValue(value any, needle string) bool {
	switch typed := value.(type) {
	case map[string]any:
		for key, item := range typed {
			if key == needle || containsJSONKeyOrValue(item, needle) {
				return true
			}
		}
		return false
	case []any:
		for _, item := range typed {
			if containsJSONKeyOrValue(item, needle) {
				return true
			}
		}
		return false
	case string:
		return typed == needle
	default:
		return false
	}
}
