package worldline

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"

	"go.temporal.io/sdk/client"
)

func TestDisabledAutoEvolutionStarterFailsClosed(t *testing.T) {
	starter := NewDisabledAutoEvolutionStarter()

	_, err := starter.StartAutoEvolution(context.Background(), StartAutoEvolutionInput{})

	if ErrorCode(err) != "WORLDLINE_AUTO_EVOLUTION_BACKEND_UNCONFIGURED" ||
		err.Error() != "worldline auto-evolution backend is not configured" {
		t.Fatalf("unexpected disabled backend error: code=%s err=%v", ErrorCode(err), err)
	}
}

func TestSQLAutoEvolutionStarterRequiresFullScopedInputAndPositiveCount(t *testing.T) {
	base := StartAutoEvolutionInput{
		TenantID: "tenant", ProjectID: "project", SessionID: "session",
		ActorUserID: "actor", RequestID: "request", MaxSteps: 1,
	}
	tests := []struct {
		name   string
		mutate func(*StartAutoEvolutionInput)
	}{
		{name: "tenant", mutate: func(input *StartAutoEvolutionInput) { input.TenantID = "" }},
		{name: "project", mutate: func(input *StartAutoEvolutionInput) { input.ProjectID = "" }},
		{name: "session", mutate: func(input *StartAutoEvolutionInput) { input.SessionID = "" }},
		{name: "actor", mutate: func(input *StartAutoEvolutionInput) { input.ActorUserID = "" }},
		{name: "request", mutate: func(input *StartAutoEvolutionInput) { input.RequestID = "" }},
		{name: "count", mutate: func(input *StartAutoEvolutionInput) { input.MaxSteps = 0 }},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			input := base
			test.mutate(&input)
			store := &recordingAutoEvolutionStore{}
			temporal := &recordingAutoEvolutionTemporalClient{}
			starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{Store: store, Client: temporal})

			_, err := starter.StartAutoEvolution(context.Background(), input)

			if ErrorCode(err) != "VALIDATION_FAILED" {
				t.Fatalf("expected validation failure, got code=%s err=%v", ErrorCode(err), err)
			}
			if store.admitCalls != 0 || temporal.calls != 0 {
				t.Fatalf("invalid input reached side effects: store=%d temporal=%d", store.admitCalls, temporal.calls)
			}
		})
	}
}

func TestSQLAutoEvolutionStarterAdmitsScopedRunAndStartsSanitizedCurrentWorldWorkflow(t *testing.T) {
	store := &recordingAutoEvolutionStore{}
	temporal := &recordingAutoEvolutionTemporalClient{}
	starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{
		Store:  store,
		Client: temporal,
		NewID: autoEvolutionFixedIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
		),
	})

	run, err := starter.StartAutoEvolution(context.Background(), StartAutoEvolutionInput{
		TenantID:    " aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa ",
		ProjectID:   " bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb ",
		SessionID:   " cccccccc-cccc-cccc-cccc-cccccccccccc ",
		ActorUserID: " dddddddd-dddd-dddd-dddd-dddddddddddd ",
		RequestID:   " request-auto-1 ",
		MaxSteps:    9,
		Options: map[string]any{
			"constraints": []any{"preserve chronology"},
			"goal_text":   "resolve the public council conflict",
			"prompt":      "private prompt",
			"branch_ids":  []any{"legacy-a", "legacy-b"},
			"nested": map[string]any{
				"credential_ref": "private credential",
				"temperature":    0.4,
			},
		},
	})

	if err != nil {
		t.Fatalf("start auto-evolution: %v", err)
	}
	if run.RunID != "11111111-1111-1111-1111-111111111111" ||
		run.ProjectID != "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" ||
		run.SessionID != "cccccccc-cccc-cccc-cccc-cccccccccccc" ||
		run.WorkflowType != WorldlineAutoEvolutionWorkflowType || run.Status != "queued" || run.MaxSteps != 9 {
		t.Fatalf("unexpected run: %#v", run)
	}
	if store.admitCalls != 1 || store.admission.EventID != "22222222-2222-2222-2222-222222222222" {
		t.Fatalf("unexpected admission: calls=%d value=%#v", store.admitCalls, store.admission)
	}
	if store.input.ActorUserID != "dddddddd-dddd-dddd-dddd-dddddddddddd" || store.input.RequestID != "request-auto-1" {
		t.Fatalf("scope was not normalized: %#v", store.input)
	}
	if _, exists := store.input.Options["prompt"]; exists {
		t.Fatalf("sensitive prompt reached admission: %#v", store.input.Options)
	}
	if _, exists := store.input.Options["branch_ids"]; exists {
		t.Fatalf("legacy branch scope reached admission: %#v", store.input.Options)
	}
	nested := store.input.Options["nested"].(map[string]any)
	if _, exists := nested["credential_ref"]; exists || nested["temperature"] != 0.4 {
		t.Fatalf("nested options were not sanitized: %#v", nested)
	}
	if temporal.calls != 1 || temporal.workflow != worldlineAutoEvolutionWorkflow {
		t.Fatalf("unexpected Temporal start: calls=%d workflow=%#v", temporal.calls, temporal.workflow)
	}
	if temporal.options.ID != "worldline_auto_evolution_11111111-1111-1111-1111-111111111111" ||
		temporal.options.TaskQueue != "worldline-interactive" {
		t.Fatalf("unexpected Temporal options: %#v", temporal.options)
	}
	if temporal.options.WorkflowExecutionTimeout != 0 || temporal.options.WorkflowRunTimeout != 0 {
		t.Fatalf("starter imposed an unexplained evolution timeout: %#v", temporal.options)
	}
	payload := temporal.args[0].(map[string]any)
	if payload["world_scope"] != "current_world" || payload["max_steps"] != 9 ||
		payload["session_id"] != "cccccccc-cccc-cccc-cccc-cccccccccccc" {
		t.Fatalf("unexpected Temporal payload: %#v", payload)
	}
	contextPayload := payload["context"].(map[string]any)
	if contextPayload["module_key"] != WorldlineAutoEvolutionModuleKey ||
		contextPayload["actor_user_id"] != "dddddddd-dddd-dddd-dddd-dddddddddddd" {
		t.Fatalf("unexpected agent context: %#v", contextPayload)
	}
}

func TestSQLAutoEvolutionStarterReplaysAdmissionWithoutSecondTemporalStart(t *testing.T) {
	existing := AutoEvolutionRun{
		RunID: "existing-run", ProjectID: "project", SessionID: "session",
		WorkflowType: WorldlineAutoEvolutionWorkflowType, Status: "running", MaxSteps: 4,
	}
	store := &recordingAutoEvolutionStore{run: existing, replayed: true}
	temporal := &recordingAutoEvolutionTemporalClient{}
	starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{
		Store: store, Client: temporal, NewID: autoEvolutionFixedIDs("unused-run", "unused-event"),
	})

	run, err := starter.StartAutoEvolution(context.Background(), validAutoEvolutionInput())

	if err != nil {
		t.Fatalf("replay auto-evolution: %v", err)
	}
	if !reflect.DeepEqual(run, existing) {
		t.Fatalf("expected existing run, got %#v", run)
	}
	if temporal.calls != 0 {
		t.Fatalf("idempotent replay started Temporal %d times", temporal.calls)
	}
}

func TestSQLAutoEvolutionStarterCompensatesTemporalFailureWithDetachedContext(t *testing.T) {
	store := &recordingAutoEvolutionStore{}
	temporal := &recordingAutoEvolutionTemporalClient{err: errors.New("private temporal provider response")}
	starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{
		Store:  store,
		Client: temporal,
		NewID: autoEvolutionFixedIDs(
			"11111111-1111-1111-1111-111111111111",
			"22222222-2222-2222-2222-222222222222",
			"33333333-3333-3333-3333-333333333333",
		),
	})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := starter.StartAutoEvolution(ctx, validAutoEvolutionInput())

	if ErrorCode(err) != "WORKFLOW_FAILED" || err.Error() != "failed to start worldline auto-evolution workflow" {
		t.Fatalf("unexpected public workflow failure: code=%s err=%v", ErrorCode(err), err)
	}
	if store.compensateCalls != 1 || store.failureEventID != "33333333-3333-3333-3333-333333333333" {
		t.Fatalf("unexpected compensation: calls=%d event=%s", store.compensateCalls, store.failureEventID)
	}
	if store.compensationContextErr != nil {
		t.Fatalf("compensation inherited cancelled request context: %v", store.compensationContextErr)
	}
	if strings.Contains(err.Error(), "provider") {
		t.Fatalf("public error leaked Temporal provider detail: %v", err)
	}
}

func TestSQLAutoEvolutionStarterSanitizesStoreAndCompensationFailures(t *testing.T) {
	t.Run("admission", func(t *testing.T) {
		store := &recordingAutoEvolutionStore{admitErr: errors.New("database api_key=private")}
		starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{
			Store: store, Client: &recordingAutoEvolutionTemporalClient{}, NewID: autoEvolutionFixedIDs("run", "event"),
		})

		_, err := starter.StartAutoEvolution(context.Background(), validAutoEvolutionInput())

		if ErrorCode(err) != "WORKFLOW_ADMISSION_FAILED" || err.Error() != "worldline auto-evolution admission failed" {
			t.Fatalf("unexpected sanitized admission error: code=%s err=%v", ErrorCode(err), err)
		}
	})

	t.Run("compensation", func(t *testing.T) {
		store := &recordingAutoEvolutionStore{compensateErr: errors.New("raw SQL manuscript body")}
		starter := NewSQLAutoEvolutionStarter(SQLAutoEvolutionStarterConfig{
			Store:  store,
			Client: &recordingAutoEvolutionTemporalClient{err: errors.New("start failed")},
			NewID:  autoEvolutionFixedIDs("run", "event", "failure-event"),
		})

		_, err := starter.StartAutoEvolution(context.Background(), validAutoEvolutionInput())

		if ErrorCode(err) != "WORKFLOW_FAILED" || err.Error() != "failed to record worldline auto-evolution start failure" {
			t.Fatalf("unexpected sanitized compensation error: code=%s err=%v", ErrorCode(err), err)
		}
	})
}

func TestAutoEvolutionQueuedEventIsCountOnlyCurrentWorldMetadata(t *testing.T) {
	input := validAutoEvolutionInput()
	input.Options = map[string]any{
		"goal_text":  "private story goal",
		"prompt":     "private provider prompt",
		"branch_ids": []any{"legacy-world"},
	}
	run := AutoEvolutionRun{SessionID: input.SessionID, MaxSteps: 13}

	raw, err := autoEvolutionQueuedEventPayload(input, run, "trace-public")
	if err != nil {
		t.Fatalf("build queued payload: %v", err)
	}
	var payload map[string]any
	if err := json.Unmarshal([]byte(raw), &payload); err != nil {
		t.Fatalf("decode queued payload: %v", err)
	}
	allowed := map[string]bool{
		"status": true, "workflow_type": true, "request_id": true, "trace_id": true,
		"session_id": true, "max_steps": true, "world_scope": true,
	}
	if len(payload) != len(allowed) {
		t.Fatalf("queued payload contained non-count metadata: %#v", payload)
	}
	for key := range payload {
		if !allowed[key] {
			t.Fatalf("queued payload exposed unexpected key %q: %#v", key, payload)
		}
	}
	if payload["max_steps"] != float64(13) || payload["world_scope"] != "current_world" {
		t.Fatalf("unexpected queued metadata: %#v", payload)
	}
	for _, forbidden := range []string{"private story goal", "private provider prompt", "legacy-world", "options", "branch"} {
		if strings.Contains(strings.ToLower(raw), strings.ToLower(forbidden)) {
			t.Fatalf("queued payload leaked %q: %s", forbidden, raw)
		}
	}
}

func TestAutoEvolutionSQLContractsPersistOnlyWorkflowMetadata(t *testing.T) {
	admission := strings.ToLower(autoEvolutionAdmissionQuery())
	for _, required := range []string{
		"from worldline_sessions", "lifecycle = 'active'", "insert into workflow_runs",
		"insert into workflow_events", "worldline_auto_evolution", "workflow.queued",
		"status = 'running'",
	} {
		if !strings.Contains(admission, required) {
			t.Fatalf("admission SQL missing %q: %s", required, admission)
		}
	}
	compensation := strings.ToLower(autoEvolutionCompensationQuery())
	for _, required := range []string{
		"update workflow_runs", "workflow.start_failed", "status = 'failed'",
		"status in ('queued', 'running')", "else 'paused'",
	} {
		if !strings.Contains(compensation, required) {
			t.Fatalf("compensation SQL missing %q: %s", required, compensation)
		}
	}
	joined := admission + compensation
	for _, forbidden := range []string{
		"insert into worldline_events", "status = 'canon'", "canon_reference",
		"branch_id", "goal_text", "prompt", "response", "credential_ref", "api_key", "manuscript", "draft",
	} {
		if strings.Contains(joined, forbidden) {
			t.Fatalf("auto-evolution SQL contains forbidden domain or sensitive field %q", forbidden)
		}
	}
}

func TestAutoEvolutionOptionsRejectLegacyWorldScopeAndRemainImmutable(t *testing.T) {
	original := map[string]any{
		"branch_id": "legacy",
		"safe":      "public constraint",
		"nested": map[string]any{
			"world_scope": "parallel-world",
			"safe":        true,
		},
	}

	sanitized := sanitizeAutoEvolutionOptions(original)

	if _, exists := sanitized["branch_id"]; exists || sanitized["safe"] != "public constraint" {
		t.Fatalf("unexpected sanitized options: %#v", sanitized)
	}
	nested := sanitized["nested"].(map[string]any)
	if _, exists := nested["world_scope"]; exists || nested["safe"] != true {
		t.Fatalf("nested world scope was not removed: %#v", nested)
	}
	if original["branch_id"] != "legacy" || original["nested"].(map[string]any)["world_scope"] != "parallel-world" {
		t.Fatalf("sanitizer mutated caller input: %#v", original)
	}
}

func validAutoEvolutionInput() StartAutoEvolutionInput {
	return StartAutoEvolutionInput{
		TenantID: "tenant", ProjectID: "project", SessionID: "session",
		ActorUserID: "actor", RequestID: "request", MaxSteps: 3,
	}
}

type recordingAutoEvolutionStore struct {
	input                  StartAutoEvolutionInput
	admission              AutoEvolutionAdmission
	run                    AutoEvolutionRun
	replayed               bool
	admitErr               error
	admitCalls             int
	compensateErr          error
	compensateCalls        int
	failureEventID         string
	compensationContextErr error
}

func (s *recordingAutoEvolutionStore) AdmitAutoEvolution(
	_ context.Context,
	input StartAutoEvolutionInput,
	admission AutoEvolutionAdmission,
) (AutoEvolutionRun, bool, error) {
	s.admitCalls++
	s.input = input
	s.admission = admission
	if s.admitErr != nil {
		return AutoEvolutionRun{}, false, s.admitErr
	}
	if s.replayed {
		return s.run, true, nil
	}
	return admission.Run, false, nil
}

func (s *recordingAutoEvolutionStore) CompensateAutoEvolutionStart(
	ctx context.Context,
	_ StartAutoEvolutionInput,
	_ AutoEvolutionRun,
	failureEventID string,
) error {
	s.compensateCalls++
	s.failureEventID = failureEventID
	s.compensationContextErr = ctx.Err()
	return s.compensateErr
}

type recordingAutoEvolutionTemporalClient struct {
	options  client.StartWorkflowOptions
	workflow any
	args     []any
	err      error
	calls    int
}

func (c *recordingAutoEvolutionTemporalClient) ExecuteWorkflow(
	_ context.Context,
	options client.StartWorkflowOptions,
	workflow any,
	args ...any,
) (client.WorkflowRun, error) {
	c.calls++
	c.options = options
	c.workflow = workflow
	c.args = args
	return nil, c.err
}

func autoEvolutionFixedIDs(ids ...string) func() string {
	index := 0
	return func() string {
		if index >= len(ids) {
			return ids[len(ids)-1]
		}
		value := ids[index]
		index++
		return value
	}
}
