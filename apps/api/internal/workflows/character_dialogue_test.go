package workflows

import (
	"context"
	"errors"
	"testing"

	"go.temporal.io/sdk/client"
)

type recordingCharacterDialogueAdmission struct {
	input       StartCharacterDialogueInput
	proposed    CharacterDialogueRun
	temporalID  string
	run         CharacterDialogueRun
	replayed    bool
	err         error
	compensated bool
}

func (s *recordingCharacterDialogueAdmission) AdmitCharacterDialogue(_ context.Context, input StartCharacterDialogueInput, proposed CharacterDialogueRun, temporalID string) (CharacterDialogueRun, bool, error) {
	s.input, s.proposed, s.temporalID = input, proposed, temporalID
	if s.err != nil {
		return CharacterDialogueRun{}, false, s.err
	}
	if s.replayed {
		return s.run, true, nil
	}
	return proposed, false, nil
}

func (s *recordingCharacterDialogueAdmission) CompensateCharacterDialogueStart(context.Context, StartCharacterDialogueInput, CharacterDialogueRun) error {
	s.compensated = true
	return nil
}

type recordingCharacterDialogueTemporalClient struct {
	options  client.StartWorkflowOptions
	workflow any
	payload  map[string]any
	err      error
}

func (c *recordingCharacterDialogueTemporalClient) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	c.options, c.workflow = options, workflow
	if len(args) == 1 {
		c.payload, _ = args[0].(map[string]any)
	}
	return nil, c.err
}

func (c *recordingCharacterDialogueTemporalClient) CancelWorkflow(context.Context, string, string) error {
	return nil
}

func TestCharacterDialogueStarterCarriesCompleteScopedContext(t *testing.T) {
	admission := &recordingCharacterDialogueAdmission{}
	temporal := &recordingCharacterDialogueTemporalClient{}
	starter := NewTemporalCharacterDialogueStarter(TemporalCharacterDialogueConfig{Client: temporal, AdmissionStore: admission})

	run, err := starter.StartCharacterDialogue(context.Background(), StartCharacterDialogueInput{
		TenantID: " tenant-1 ", ProjectID: " project-1 ", InteractionID: " interaction-1 ",
		UserTurnID: " turn-1 ", ActorUserID: " actor-1 ", RequestID: " request-1 ",
	})
	if err != nil {
		t.Fatalf("start character dialogue: %v", err)
	}
	if run.Status != "queued" || run.WorkflowType != CharacterDialogueWorkflowType || run.TraceID == "" {
		t.Fatalf("unexpected run: %#v", run)
	}
	if temporal.workflow != CharacterDialogueWorkflowName || temporal.options.TaskQueue != CharacterDialogueTaskQueue {
		t.Fatalf("unexpected Temporal handoff: workflow=%v options=%#v", temporal.workflow, temporal.options)
	}
	contextPayload, _ := temporal.payload["context"].(map[string]any)
	permissions, _ := contextPayload["permissions"].(map[string][]string)
	if contextPayload["tenant_id"] != "tenant-1" || contextPayload["project_id"] != "project-1" ||
		contextPayload["actor_user_id"] != "actor-1" || contextPayload["module_key"] != CharacterDialogueModuleKey ||
		temporal.payload["interaction_id"] != "interaction-1" || temporal.payload["session_id"] != "interaction-1" ||
		temporal.payload["user_turn_id"] != "turn-1" || len(permissions[CharacterDialogueModuleKey]) != 1 {
		t.Fatalf("lost character dialogue context: %#v", temporal.payload)
	}
}

func TestCharacterDialogueStarterReplaysAdmissionWithoutDuplicateTemporalStart(t *testing.T) {
	existing := CharacterDialogueRun{RunID: "run-existing", TraceID: "trace-existing", ProjectID: "project-1", InteractionID: "interaction-1", WorkflowType: CharacterDialogueWorkflowType, Status: "completed"}
	admission := &recordingCharacterDialogueAdmission{run: existing, replayed: true}
	temporal := &recordingCharacterDialogueTemporalClient{}
	starter := NewTemporalCharacterDialogueStarter(TemporalCharacterDialogueConfig{Client: temporal, AdmissionStore: admission})

	run, err := starter.StartCharacterDialogue(context.Background(), StartCharacterDialogueInput{
		TenantID: "tenant-1", ProjectID: "project-1", InteractionID: "interaction-1",
		UserTurnID: "turn-1", ActorUserID: "actor-1", RequestID: "request-1",
	})
	if err != nil || run.RunID != existing.RunID {
		t.Fatalf("expected replayed run, run=%#v err=%v", run, err)
	}
	if temporal.workflow != nil {
		t.Fatalf("Temporal started for replay: %v", temporal.workflow)
	}
}

func TestCharacterDialogueStarterCompensatesSanitizedTemporalFailure(t *testing.T) {
	admission := &recordingCharacterDialogueAdmission{}
	temporal := &recordingCharacterDialogueTemporalClient{err: errors.New("provider raw prompt api_key=secret")}
	starter := NewTemporalCharacterDialogueStarter(TemporalCharacterDialogueConfig{Client: temporal, AdmissionStore: admission})

	_, err := starter.StartCharacterDialogue(context.Background(), StartCharacterDialogueInput{
		TenantID: "tenant-1", ProjectID: "project-1", InteractionID: "interaction-1",
		UserTurnID: "turn-1", ActorUserID: "actor-1", RequestID: "request-1",
	})
	if ErrorCode(err) != "WORKFLOW_FAILED" || err.Error() != "failed to start character dialogue workflow" {
		t.Fatalf("unexpected public error: %v", err)
	}
	if !admission.compensated {
		t.Fatal("expected start failure compensation")
	}
}

func TestCharacterDialogueStarterFailsClosedWithoutBackend(t *testing.T) {
	starter := NewTemporalCharacterDialogueStarter(TemporalCharacterDialogueConfig{})
	_, err := starter.StartCharacterDialogue(context.Background(), StartCharacterDialogueInput{
		TenantID: "tenant-1", ProjectID: "project-1", InteractionID: "interaction-1",
		UserTurnID: "turn-1", ActorUserID: "actor-1",
	})
	if ErrorCode(err) != "CHARACTER_DIALOGUE_BACKEND_UNCONFIGURED" {
		t.Fatalf("unexpected error: %v", err)
	}
}
