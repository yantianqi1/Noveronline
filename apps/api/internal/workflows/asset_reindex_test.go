package workflows

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func TestDisabledAssetReindexStarterFailsClosed(t *testing.T) {
	starter := NewDisabledAssetReindexStarter()

	_, err := starter.StartAssetReindex(context.Background(), StartAssetReindexInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if code := ErrorCode(err); code != "ASSET_REINDEX_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected asset reindex backend to fail closed, got %s (%v)", code, err)
	}
}

func TestTemporalAssetReindexStarterStartsWorkflowWithoutWaitingForCompletion(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalAssetReindexStarter(TemporalAssetReindexConfig{
		Client:    temporalClient,
		TaskQueue: AssetIngestionTaskQueue,
	})

	run, err := starter.StartAssetReindex(context.Background(), StartAssetReindexInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		Scope:       "project",
		Mode:        "keyword",
		Options: map[string]any{
			"include_disabled": false,
			"prompt":           "must be removed before workflow payload",
			"content":          "must be removed before workflow payload",
		},
	})

	if err != nil {
		t.Fatalf("start asset reindex: %v", err)
	}
	if run.RunID == "" || run.ProjectID != "project-1" || run.WorkflowType != AssetReindexWorkflowType || run.Status != "queued" {
		t.Fatalf("unexpected asset reindex run: %#v", run)
	}
	requireUUIDRunID(t, run.RunID)
	if temporalClient.options.TaskQueue != AssetIngestionTaskQueue || temporalClient.options.ID != "asset_reindex_"+run.RunID {
		t.Fatalf("unexpected workflow options: %#v", temporalClient.options)
	}
	if temporalClient.workflow != AssetReindexWorkflowName {
		t.Fatalf("unexpected workflow name: %#v", temporalClient.workflow)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected asset reindex workflow payload map, got %#v", temporalClient.args)
	}
	if payload["tenant_id"] != "tenant-1" || payload["project_id"] != "project-1" || payload["run_id"] != run.RunID {
		t.Fatalf("lost run context payload: %#v", payload)
	}
	if payload["workflow_type"] != AssetReindexWorkflowType || payload["trace_id"] == "" {
		t.Fatalf("lost workflow metadata: %#v", payload)
	}
	if payload["actor_user_id"] != "user-1" || payload["request_id"] != "req-1" {
		t.Fatalf("lost actor/request metadata: %#v", payload)
	}
	if payload["scope"] != "project" || payload["mode"] != "keyword" {
		t.Fatalf("lost asset reindex request metadata: %#v", payload)
	}
	contextPayload, ok := payload["context"].(map[string]any)
	if !ok {
		t.Fatalf("expected context payload, got %#v", payload["context"])
	}
	if contextPayload["tenant_id"] != "tenant-1" || contextPayload["project_id"] != "project-1" || contextPayload["run_id"] != run.RunID {
		t.Fatalf("lost agent context: %#v", contextPayload)
	}
	if contextPayload["module_key"] != AssetReindexModuleKey || contextPayload["workflow_type"] != AssetReindexWorkflowType {
		t.Fatalf("lost module/workflow context: %#v", contextPayload)
	}
	permissions := contextPayload["permissions"].(map[string][]string)
	if got := permissions[AssetReindexModuleKey][0]; got != "run" {
		t.Fatalf("expected asset reindex permission, got %#v", permissions)
	}
	payloadJSON := mapToJSONForTest(t, payload)
	for _, forbidden := range []string{"prompt", "response", "api_key", "encrypted_api_key", "credential_ref", "content", "body", "embedding_chunk"} {
		if strings.Contains(payloadJSON, forbidden) {
			t.Fatalf("asset reindex workflow payload leaked forbidden field %q: %s", forbidden, payloadJSON)
		}
	}
}

func TestTemporalAssetReindexStarterPersistsAdmissionBeforeStartingWorkflow(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	admissionStore := &recordingAssetReindexAdmissionStore{
		temporalStarted: func() bool { return temporalClient.started },
	}
	starter := NewTemporalAssetReindexStarter(TemporalAssetReindexConfig{
		Client:         temporalClient,
		TaskQueue:      AssetIngestionTaskQueue,
		AdmissionStore: admissionStore,
	})

	run, err := starter.StartAssetReindex(context.Background(), StartAssetReindexInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		RequestID:   "req-1",
		Scope:       "project",
		Mode:        "keyword",
	})

	if err != nil {
		t.Fatalf("start asset reindex: %v", err)
	}
	if admissionStore.temporalWasStartedWhenCalled {
		t.Fatal("asset reindex admission must be persisted before Temporal starts")
	}
	if admissionStore.input.TenantID != "tenant-1" || admissionStore.input.ProjectID != "project-1" || admissionStore.input.RunID != run.RunID {
		t.Fatalf("admission lost tenant/project/run context: %#v", admissionStore.input)
	}
	if admissionStore.input.WorkflowType != AssetReindexWorkflowType || admissionStore.input.TemporalWorkflowID != "asset_reindex_"+run.RunID {
		t.Fatalf("admission lost workflow metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.ActorUserID != "user-1" || admissionStore.input.RequestID != "req-1" {
		t.Fatalf("admission lost actor/request metadata: %#v", admissionStore.input)
	}
	if admissionStore.input.Scope != "project" || admissionStore.input.Mode != "keyword" || admissionStore.input.Status != "queued" {
		t.Fatalf("admission lost public request metadata: %#v", admissionStore.input)
	}
}

func TestTemporalAssetReindexStarterDoesNotStartWorkflowWhenAdmissionFails(t *testing.T) {
	temporalClient := &recordingSeedTemporalClient{}
	starter := NewTemporalAssetReindexStarter(TemporalAssetReindexConfig{
		Client:    temporalClient,
		TaskQueue: AssetIngestionTaskQueue,
		AdmissionStore: &recordingAssetReindexAdmissionStore{
			err: errors.New("insert workflow_runs failed"),
		},
	})

	_, err := starter.StartAssetReindex(context.Background(), StartAssetReindexInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		Scope:     "project",
		Mode:      "keyword",
	})

	if code := ErrorCode(err); code != "WORKFLOW_ADMISSION_FAILED" {
		t.Fatalf("expected asset reindex admission failure, got %s (%v)", code, err)
	}
	if temporalClient.started {
		t.Fatal("Temporal workflow should not start when asset reindex admission persistence fails")
	}
}

func TestSQLAssetReindexAdmissionStorePersistsWorkflowRunAndQueuedEventWithoutSensitivePayload(t *testing.T) {
	execer := &recordingWriterAdmissionExecer{}
	store := NewSQLAssetReindexAdmissionStore(SQLAssetReindexAdmissionStoreConfig{Execer: execer})

	err := store.AdmitAssetReindexRun(context.Background(), AssetReindexAdmissionInput{
		TenantID:           "11111111-1111-4111-8111-111111111111",
		ProjectID:          "22222222-2222-4222-8222-222222222222",
		RunID:              "33333333-3333-4333-8333-333333333333",
		TraceID:            "trace_33333333-3333-4333-8333-333333333333",
		WorkflowType:       AssetReindexWorkflowType,
		TemporalWorkflowID: "asset_reindex_33333333-3333-4333-8333-333333333333",
		ActorUserID:        "44444444-4444-4444-8444-444444444444",
		RequestID:          "req-asset-reindex",
		Scope:              "project",
		Mode:               "keyword",
		Status:             "queued",
	})

	if err != nil {
		t.Fatalf("admit asset reindex run: %v", err)
	}
	if !strings.Contains(execer.query, "INSERT INTO workflow_runs") || !strings.Contains(execer.query, "INSERT INTO workflow_events") {
		t.Fatalf("expected workflow run/event inserts, got %s", execer.query)
	}
	if strings.Contains(execer.query, "assets") || strings.Contains(execer.query, "global_search_index") {
		t.Fatalf("asset reindex admission should not create assets/search rows: %s", execer.query)
	}
	joinedArgs := strings.Join(argsAsStrings(execer.args), "\n")
	for _, forbidden := range []string{"raw novel text", "search body", "embedding_chunk", "credential_ref", "api_key", "encrypted_api_key", "prompt", "response", "body", "content", "draft", "manuscript"} {
		if strings.Contains(joinedArgs, forbidden) {
			t.Fatalf("asset reindex admission SQL args leaked sensitive field %q: %s", forbidden, joinedArgs)
		}
	}
	if !strings.Contains(joinedArgs, "req-asset-reindex") || !strings.Contains(joinedArgs, "project") || !strings.Contains(joinedArgs, "keyword") {
		t.Fatalf("expected public request metadata in admission args, got %s", joinedArgs)
	}
	if _, err := json.Marshal(execer.args); err != nil {
		t.Fatalf("expected admission args to be JSON-safe: %v", err)
	}
}

type recordingAssetReindexAdmissionStore struct {
	input                        AssetReindexAdmissionInput
	err                          error
	temporalStarted              func() bool
	temporalWasStartedWhenCalled bool
}

func (s *recordingAssetReindexAdmissionStore) AdmitAssetReindexRun(_ context.Context, input AssetReindexAdmissionInput) error {
	s.input = input
	if s.temporalStarted != nil {
		s.temporalWasStartedWhenCalled = s.temporalStarted()
	}
	return s.err
}
