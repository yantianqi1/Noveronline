package workflows

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func TestDisabledStoryGraphBuildStarterFailsClosed(t *testing.T) {
	starter := NewDisabledStoryGraphBuildStarter()

	_, err := starter.StartStoryGraphBuild(context.Background(), StartStoryGraphBuildInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if code := ErrorCode(err); code != "STORY_GRAPH_BUILD_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected story graph build backend to fail closed, got %s (%v)", code, err)
	}
}

func TestDisabledStoryGraphBondGenerationStarterFailsClosed(t *testing.T) {
	starter := NewDisabledStoryGraphBondGenerationStarter()

	_, err := starter.StartStoryGraphBondGeneration(context.Background(), StartStoryGraphBondGenerationInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		NodeIDs:   []string{"node-1", "node-2"},
	})

	if code := ErrorCode(err); code != "STORY_GRAPH_BOND_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected story graph bond backend to fail closed, got %s (%v)", code, err)
	}
}

func TestTemporalStoryGraphBondGenerationStarterStartsWorkflowWithSanitizedPayload(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalStoryGraphBondGenerationStarter(TemporalStoryGraphBondGenerationConfig{
		Client:    temporalClient,
		TaskQueue: StoryGraphTaskQueue,
	})

	run, err := starter.StartStoryGraphBondGeneration(context.Background(), StartStoryGraphBondGenerationInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		GraphID:     "graph-1",
		NodeIDs:     []string{"node-1", " node-2 ", "node-1", ""},
		Focus:       "rain treaty",
		Options: map[string]any{
			"generate_bonds":   true,
			"generate_threads": true,
			"prompt":           "must be removed",
			"nested":           map[string]any{"content": "hidden"},
		},
	})

	if err != nil {
		t.Fatalf("start story graph bond generation: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-1" || run.WorkflowType != StoryGraphBondGenerationWorkflowType || run.Status != "queued" {
		t.Fatalf("unexpected story graph bond run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if temporalClient.options.TaskQueue != StoryGraphTaskQueue || temporalClient.options.ID != "story_graph_bond_generation_"+run.RunID {
		t.Fatalf("unexpected workflow options: %#v", temporalClient.options)
	}
	if temporalClient.workflow != StoryGraphBondGenerationWorkflowName {
		t.Fatalf("unexpected workflow name: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected story graph bond workflow payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != "tenant-1" || payload["project_id"] != "project-1" || payload["run_id"] != run.RunID {
		t.Fatalf("lost run context payload: %#v", payload)
	}
	if payload["workflow_type"] != StoryGraphBondGenerationWorkflowType || payload["module_key"] != StoryGraphBondGenerationModuleKey || payload["trace_id"] == "" {
		t.Fatalf("lost workflow metadata: %#v", payload)
	}
	if payload["actor_user_id"] != "user-1" || payload["request_id"] != "req-1" || payload["graph_id"] != "graph-1" || payload["focus"] != "rain treaty" {
		t.Fatalf("lost actor/request/selection metadata: %#v", payload)
	}
	if strings.Join(payload["node_ids"].([]string), ",") != "node-1,node-2" {
		t.Fatalf("expected normalized node ids, got %#v", payload["node_ids"])
	}
	contextPayload, ok := payload["context"].(map[string]any)
	if !ok {
		t.Fatalf("expected context payload, got %#v", payload["context"])
	}
	if contextPayload["tenant_id"] != "tenant-1" || contextPayload["project_id"] != "project-1" || contextPayload["run_id"] != run.RunID {
		t.Fatalf("lost agent context: %#v", contextPayload)
	}
	if contextPayload["module_key"] != StoryGraphBondGenerationModuleKey || contextPayload["workflow_type"] != StoryGraphBondGenerationWorkflowType {
		t.Fatalf("lost module/workflow context: %#v", contextPayload)
	}
	permissions := contextPayload["permissions"].(map[string][]string)
	if got := permissions[StoryGraphBondGenerationModuleKey][0]; got != "run" {
		t.Fatalf("expected story graph bond permission, got %#v", permissions)
	}
	payloadJSON := mapToJSONForTest(t, payload)
	for _, forbidden := range []string{"prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "content", "body", "raw_text", "snippet"} {
		if strings.Contains(payloadJSON, forbidden) {
			t.Fatalf("story graph bond workflow payload leaked forbidden field %q: %s", forbidden, payloadJSON)
		}
	}
}

func TestTemporalStoryGraphBondGenerationStarterPersistsAdmissionBeforeStartingWorkflow(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	admissionStore := &recordingStoryGraphBondGenerationAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalStoryGraphBondGenerationStarter(TemporalStoryGraphBondGenerationConfig{
		Client:         temporalClient,
		TaskQueue:      StoryGraphTaskQueue,
		AdmissionStore: admissionStore,
	})

	run, err := starter.StartStoryGraphBondGeneration(context.Background(), StartStoryGraphBondGenerationInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		GraphID:     "graph-1",
		NodeIDs:     []string{"node-1", "node-2"},
		Focus:       "rain treaty",
	})

	if err != nil {
		t.Fatalf("start story graph bond generation: %v", err)
	}
	if admissionStore.temporalWasStartedWhenCalled {
		t.Fatal("story graph bond admission must be persisted before Temporal starts")
	}
	if admissionStore.input.TenantID != "tenant-1" || admissionStore.input.ProjectID != "project-1" || admissionStore.input.RunID != run.RunID {
		t.Fatalf("admission lost tenant/project/run context: %#v", admissionStore.input)
	}
	if admissionStore.input.WorkflowType != StoryGraphBondGenerationWorkflowType || admissionStore.input.TemporalWorkflowID != "story_graph_bond_generation_"+run.RunID {
		t.Fatalf("admission lost workflow metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.ActorUserID != "user-1" || admissionStore.input.RequestID != "req-1" || admissionStore.input.GraphID != "graph-1" || admissionStore.input.NodeCount != 2 || !admissionStore.input.HasFocus {
		t.Fatalf("admission lost public selection metadata: %#v", admissionStore.input)
	}
}

func TestTemporalStoryGraphBondGenerationStarterDoesNotStartWorkflowWhenAdmissionFails(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalStoryGraphBondGenerationStarter(TemporalStoryGraphBondGenerationConfig{
		Client:    temporalClient,
		TaskQueue: StoryGraphTaskQueue,
		AdmissionStore: &recordingStoryGraphBondGenerationAdmissionStore{
			err: errors.New("insert workflow_runs failed"),
		},
	})

	_, err := starter.StartStoryGraphBondGeneration(context.Background(), StartStoryGraphBondGenerationInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		NodeIDs:   []string{"node-1", "node-2"},
	})

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected story graph bond admission failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when story graph bond admission persistence fails")
	}
}

func TestSQLStoryGraphBondGenerationAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLStoryGraphBondGenerationAdmissionStore(SQLStoryGraphBondGenerationAdmissionStoreConfig{Execer: execer})

	err := store.AdmitStoryGraphBondGeneration(context.Background(), StoryGraphBondGenerationAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       StoryGraphBondGenerationWorkflowType,
		TemporalWorkflowID: "story_graph_bond_generation_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-story-graph-bond",
		GraphID:            "graph-1",
		NodeCount:          2,
		HasFocus:           true,
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit story graph bond generation: %v", err)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") || !strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected workflow run/event inserts, got %s", execer.query)
	}
	if strings.Contains(execer.query, "story_graph_edges") || strings.Contains(execer.query, "plot_threads") || strings.Contains(execer.query, "relationships") {
		t.Fatalf("bond generation admission should not create candidate/canon rows: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"node-1", "node-2", "rain treaty", "raw novel text", "snippet", "credential_ref", "api_key", "encrypted_api_key", "prompt", "response", "body", "content", "draft", "manuscript"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("story graph bond admission SQL args leaked sensitive field %q: %s", forbidden, joinedArgs)
		}
	}
	for _, expected := range []string{"req-story-graph-bond", "graph-1", "graph_bond_generator", "2"} {
		if !strings.Contains(joinedArgs, expected) {
			t.Fatalf("expected public metadata %q in admission args, got %s", expected, joinedArgs)
		}
	}
	if _, err := json.Marshal(execer.args); err != nil {
		t.Fatalf("expected admission args to be JSON-safe: %v", err)
	}
}

func TestSQLStoryGraphBondGenerationAdmissionStoreUsesTenantContext(t *testing.T) {
	execer := &recordingTenantWriterAdmissionExecer{}
	store := NewSQLStoryGraphBondGenerationAdmissionStore(SQLStoryGraphBondGenerationAdmissionStoreConfig{Execer: execer})

	err := store.AdmitStoryGraphBondGeneration(context.Background(), StoryGraphBondGenerationAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		WorkflowType:       StoryGraphBondGenerationWorkflowType,
		TemporalWorkflowID: "story_graph_bond_generation_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		GraphID:            "graph-1",
		NodeCount:          2,
	})

	if err != nil {
		t.Fatalf("admit story graph bond generation: %v", err)
	}
	if execer.plainCalled {
		t.Fatal("story graph bond admission must not bypass tenant context")
	}
	if execer.tenantID != "11111111-1111-4111-8111-111111111111" || execer.projectID != "22222222-2222-4222-8222-222222222222" {
		t.Fatalf("unexpected tenant context: tenant=%q project=%q", execer.tenantID, execer.projectID)
	}
}

func TestTemporalStoryGraphBuildStarterStartsWorkflowWithSanitizedPayload(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalStoryGraphBuildStarter(TemporalStoryGraphBuildConfig{
		Client:    temporalClient,
		TaskQueue: StoryGraphTaskQueue,
	})

	run, err := starter.StartStoryGraphBuild(context.Background(), StartStoryGraphBuildInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		Mode:        "full",
		Options: map[string]any{
			"source": "seed_canon",
			"prompt": "must be removed",
			"nested": map[string]any{"content": "hidden"},
		},
	})

	if err != nil {
		t.Fatalf("start story graph build: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-1" || run.WorkflowType != StoryGraphBuildWorkflowType || run.Status != "queued" {
		t.Fatalf("unexpected story graph build run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if temporalClient.options.TaskQueue != StoryGraphTaskQueue || temporalClient.options.ID != "story_graph_build_"+run.RunID {
		t.Fatalf("unexpected workflow options: %#v", temporalClient.options)
	}
	if temporalClient.workflow != StoryGraphBuildWorkflowName {
		t.Fatalf("unexpected workflow name: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected story graph workflow payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != "tenant-1" || payload["project_id"] != "project-1" || payload["run_id"] != run.RunID {
		t.Fatalf("lost run context payload: %#v", payload)
	}
	if payload["workflow_type"] != StoryGraphBuildWorkflowType || payload["trace_id"] == "" {
		t.Fatalf("lost workflow metadata: %#v", payload)
	}
	if payload["actor_user_id"] != "user-1" || payload["request_id"] != "req-1" || payload["mode"] != "full" {
		t.Fatalf("lost actor/request/build metadata: %#v", payload)
	}
	contextPayload, ok := payload["context"].(map[string]any)
	if !ok {
		t.Fatalf("expected context payload, got %#v", payload["context"])
	}
	if contextPayload["tenant_id"] != "tenant-1" || contextPayload["project_id"] != "project-1" || contextPayload["run_id"] != run.RunID {
		t.Fatalf("lost agent context: %#v", contextPayload)
	}
	if contextPayload["module_key"] != StoryGraphBuildModuleKey || contextPayload["workflow_type"] != StoryGraphBuildWorkflowType {
		t.Fatalf("lost module/workflow context: %#v", contextPayload)
	}
	permissions := contextPayload["permissions"].(map[string][]string)
	if got := permissions[StoryGraphBuildModuleKey][0]; got != "run" {
		t.Fatalf("expected story graph build permission, got %#v", permissions)
	}
	payloadJSON := mapToJSONForTest(t, payload)
	for _, forbidden := range []string{"prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "content", "body", "raw_text", "snippet"} {
		if strings.Contains(payloadJSON, forbidden) {
			t.Fatalf("story graph workflow payload leaked forbidden field %q: %s", forbidden, payloadJSON)
		}
	}
}

func TestTemporalStoryGraphBuildStarterPersistsAdmissionBeforeStartingWorkflow(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	admissionStore := &recordingStoryGraphBuildAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalStoryGraphBuildStarter(TemporalStoryGraphBuildConfig{
		Client:         temporalClient,
		TaskQueue:      StoryGraphTaskQueue,
		AdmissionStore: admissionStore,
	})

	run, err := starter.StartStoryGraphBuild(context.Background(), StartStoryGraphBuildInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		Mode:        "incremental",
	})

	if err != nil {
		t.Fatalf("start story graph build: %v", err)
	}
	if admissionStore.temporalWasStartedWhenCalled {
		t.Fatal("story graph admission must be persisted before Temporal starts")
	}
	if admissionStore.input.TenantID != "tenant-1" || admissionStore.input.ProjectID != "project-1" || admissionStore.input.RunID != run.RunID {
		t.Fatalf("admission lost tenant/project/run context: %#v", admissionStore.input)
	}
	if admissionStore.input.WorkflowType != StoryGraphBuildWorkflowType || admissionStore.input.TemporalWorkflowID != "story_graph_build_"+run.RunID {
		t.Fatalf("admission lost workflow metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.ActorUserID != "user-1" || admissionStore.input.RequestID != "req-1" || admissionStore.input.Mode != "incremental" {
		t.Fatalf("admission lost public build metadata: %#v", admissionStore.input)
	}
}

func TestTemporalStoryGraphBuildStarterDoesNotStartWorkflowWhenAdmissionFails(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalStoryGraphBuildStarter(TemporalStoryGraphBuildConfig{
		Client:    temporalClient,
		TaskQueue: StoryGraphTaskQueue,
		AdmissionStore: &recordingStoryGraphBuildAdmissionStore{
			err: errors.New("insert workflow_runs failed"),
		},
	})

	_, err := starter.StartStoryGraphBuild(context.Background(), StartStoryGraphBuildInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected story graph admission failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when story graph admission persistence fails")
	}
}

func TestSQLStoryGraphBuildAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLStoryGraphBuildAdmissionStore(SQLStoryGraphBuildAdmissionStoreConfig{Execer: execer})

	err := store.AdmitStoryGraphBuild(context.Background(), StoryGraphBuildAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       StoryGraphBuildWorkflowType,
		TemporalWorkflowID: "story_graph_build_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-story-graph",
		Mode:               "full",
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit story graph build: %v", err)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") || !strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected workflow run/event inserts, got %s", execer.query)
	}
	if strings.Contains(execer.query, "story_graph_nodes") || strings.Contains(execer.query, "story_graph_edges") {
		t.Fatalf("story graph admission should not create graph rows: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"raw novel text", "seed analysis body", "snippet", "credential_ref", "api_key", "encrypted_api_key", "prompt", "response", "body", "content", "draft", "manuscript"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("story graph admission SQL args leaked sensitive field %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, "req-story-graph") || !strings.Contains(joinedArgs, "full") {
		t.Fatalf("expected public request metadata in admission args, got %s", joinedArgs)
	}
	if _, err := json.Marshal(execer.args); err != nil {
		t.Fatalf("expected admission args to be JSON-safe: %v", err)
	}
}

func TestSQLStoryGraphBuildAdmissionStoreUsesTenantContext(t *testing.T) {
	execer := &recordingTenantWriterAdmissionExecer{}
	store := NewSQLStoryGraphBuildAdmissionStore(SQLStoryGraphBuildAdmissionStoreConfig{Execer: execer})

	err := store.AdmitStoryGraphBuild(context.Background(), StoryGraphBuildAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		WorkflowType:       StoryGraphBuildWorkflowType,
		TemporalWorkflowID: "story_graph_build_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
	})

	if err != nil {
		t.Fatalf("admit story graph build: %v", err)
	}
	if execer.plainCalled {
		t.Fatal("story graph admission must not bypass tenant context")
	}
	if execer.tenantID != "11111111-1111-4111-8111-111111111111" || execer.projectID != "22222222-2222-4222-8222-222222222222" {
		t.Fatalf("unexpected tenant context: tenant=%q project=%q", execer.tenantID, execer.projectID)
	}
}

type recordingStoryGraphBuildAdmissionStore struct {
	input                        StoryGraphBuildAdmissionInput
	err                          error
	temporalStarted              func() bool
	temporalWasStartedWhenCalled bool
}

func (s *recordingStoryGraphBuildAdmissionStore) AdmitStoryGraphBuild(_ context.Context, input StoryGraphBuildAdmissionInput) error {
	s.input = input
	if s.temporalStarted != nil {
		s.temporalWasStartedWhenCalled = s.temporalStarted()
	}
	return s.err
}

type recordingStoryGraphBondGenerationAdmissionStore struct {
	input                        StoryGraphBondGenerationAdmissionInput
	err                          error
	temporalStarted              func() bool
	temporalWasStartedWhenCalled bool
}

func (s *recordingStoryGraphBondGenerationAdmissionStore) AdmitStoryGraphBondGeneration(_ context.Context, input StoryGraphBondGenerationAdmissionInput) error {
	s.input = input
	if s.temporalStarted != nil {
		s.temporalWasStartedWhenCalled = s.temporalStarted()
	}
	return s.err
}
